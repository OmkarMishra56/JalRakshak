from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..routing import suggest_route

router = APIRouter(prefix="/routes", tags=["routes"])


@router.get("/suggest")
async def suggest(start_zone_id: str, end_zone_id: str, db: AsyncSession = Depends(get_db)):
    result = await suggest_route(db, start_zone_id, end_zone_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No route found between these zones")
    return {
        "avoids_severe": result.avoids_severe,
        "total_distance_km": result.total_distance_km,
        "waypoints": [
            {
                "zone_id": z.id, "name": z.name, "code": z.code,
                "lat": z.centroid_lat, "lng": z.centroid_lng, "status": z.current_status.value,
            }
            for z in result.zone_path
        ],
    }
