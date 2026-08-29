"""
Basic route suggestion: avoid severe (red) zones.

This is a deliberately lightweight zone-graph pathfinder, not a full road-network
router (that would need OSRM/GraphHopper + real street data -- see README for how
to swap this out for one). Here we:

  1. Build a graph where nodes are zone centroids and edges connect zones whose
     polygons share a border (ST_Touches) or are within a small buffer of each
     other (handles zones that don't perfectly tile).
  2. Weight each edge by the *destination* zone's current risk: severe zones cost
     dramatically more to traverse, moderate zones cost a bit more, safe zones
     cost their plain distance.
  3. Run Dijkstra from the start zone to the destination zone.
  4. Return the ordered list of zone waypoints plus a flag on the whole route:
     "does this path avoid all severe zones or was one unavoidable".

Good enough to say "go this way, not through the flooded ward" on a live map;
not a turn-by-turn street router.
"""
import heapq
import math
from dataclasses import dataclass

from geoalchemy2.functions import ST_Touches, ST_DWithin
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Zone, ZoneStatus

SEVERE_PENALTY = 50.0
MODERATE_PENALTY = 8.0


def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


@dataclass
class RouteResult:
    zone_path: list[Zone]
    avoids_severe: bool
    total_distance_km: float


async def _build_adjacency(db: AsyncSession, zones: list[Zone]) -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = {z.id: [] for z in zones}
    for i, a in enumerate(zones):
        for b in zones[i + 1:]:
            touches = (
                await db.execute(select(ST_Touches(a.geom, b.geom)))
            ).scalar_one()
            near = False
            if not touches:
                near = (
                    await db.execute(select(ST_DWithin(a.geom, b.geom, 0.01)))  # ~1.1km in degrees, coarse
                ).scalar_one()
            if touches or near:
                adjacency[a.id].append(b.id)
                adjacency[b.id].append(a.id)
    return adjacency


def _edge_cost(from_zone: Zone, to_zone: Zone) -> float:
    dist = _haversine_km(from_zone.centroid_lat, from_zone.centroid_lng, to_zone.centroid_lat, to_zone.centroid_lng)
    penalty = 0.0
    if to_zone.current_status == ZoneStatus.severe:
        penalty = SEVERE_PENALTY
    elif to_zone.current_status == ZoneStatus.moderate:
        penalty = MODERATE_PENALTY
    return dist + penalty


async def suggest_route(db: AsyncSession, start_zone_id: str, end_zone_id: str) -> RouteResult | None:
    zones = (await db.execute(select(Zone))).scalars().all()
    zone_by_id = {z.id: z for z in zones}
    if start_zone_id not in zone_by_id or end_zone_id not in zone_by_id:
        return None

    adjacency = await _build_adjacency(db, zones)

    # Dijkstra
    dist = {z.id: math.inf for z in zones}
    prev: dict[str, str | None] = {z.id: None for z in zones}
    dist[start_zone_id] = 0.0
    pq = [(0.0, start_zone_id)]
    visited = set()

    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == end_zone_id:
            break
        for v in adjacency.get(u, []):
            cost = _edge_cost(zone_by_id[u], zone_by_id[v])
            nd = d + cost
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))

    if dist[end_zone_id] == math.inf:
        return None  # no connected path found (disconnected zone graph)

    # Reconstruct path
    path_ids = []
    cur: str | None = end_zone_id
    while cur is not None:
        path_ids.append(cur)
        cur = prev[cur]
    path_ids.reverse()

    zone_path = [zone_by_id[zid] for zid in path_ids]
    avoids_severe = all(z.current_status != ZoneStatus.severe for z in zone_path)
    total_km = sum(
        _haversine_km(
            zone_path[i].centroid_lat, zone_path[i].centroid_lng,
            zone_path[i + 1].centroid_lat, zone_path[i + 1].centroid_lng,
        )
        for i in range(len(zone_path) - 1)
    )
    return RouteResult(zone_path=zone_path, avoids_severe=avoids_severe, total_distance_km=round(total_km, 2))
