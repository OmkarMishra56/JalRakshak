"use client";
/**
 * Live map: renders each zone as a color-coded polygon (green/yellow/red),
 * updates in place via WebSocket (no refetch/reload), and lets the user tap
 * a zone to open the detail panel.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Popup, useMap } from "react-leaflet";
import type { Zone } from "@/lib/api";
import "leaflet/dist/leaflet.css";

const STATUS_COLOR: Record<string, string> = {
  safe: "#22C55E",
  moderate: "#F5B93D",
  severe: "#EF4444",
};

const STATUS_LABEL: Record<string, string> = {
  safe: "Safe",
  moderate: "Moderate",
  severe: "Severe",
};

function FlashOnUpdate({ flashZoneId }: { flashZoneId: string | null }) {
  // Placeholder hook point for future map-level flash effects (kept simple: the
  // GeoJSON re-render + CSS pulse on severe zones already communicates change).
  return null;
}

export default function MapView({
  zones,
  onSelectZone,
  selectedZoneId,
  centerLat,
  centerLng,
}: {
  zones: Zone[];
  onSelectZone: (zoneId: string) => void;
  selectedZoneId: string | null;
  centerLat: number;
  centerLng: number;
}) {
  const styleFor = useMemo(
    () => (zone: Zone) => ({
      color: STATUS_COLOR[zone.current_status],
      weight: zone.id === selectedZoneId ? 3 : 1.5,
      fillColor: STATUS_COLOR[zone.current_status],
      fillOpacity: zone.current_status === "severe" ? 0.35 : zone.current_status === "moderate" ? 0.22 : 0.12,
    }),
    [selectedZoneId]
  );

  return (
    <MapContainer
      center={[centerLat, centerLng]}
      zoom={12}
      className="h-full w-full"
      zoomControl={false}
    >
      <TileLayer
        attribution='&copy; <a href="https://carto.com/attributions">CARTO</a> &copy; OpenStreetMap contributors'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />
      {zones.map((zone) => (
        <GeoJSON
          key={`${zone.id}-${zone.current_status}-${zone.current_score}`}
          data={zone.geojson as any}
          style={() => styleFor(zone)}
          eventHandlers={{ click: () => onSelectZone(zone.id) }}
        >
          <Popup>
            <div className="font-mono text-xs">
              <div className="font-semibold text-sm mb-1">{zone.name}</div>
              <div>Status: <span style={{ color: STATUS_COLOR[zone.current_status] }}>{STATUS_LABEL[zone.current_status]}</span></div>
              <div>Score: {zone.current_score.toFixed(0)}/100</div>
            </div>
          </Popup>
        </GeoJSON>
      ))}
      {zones
        .filter((z) => z.current_status === "severe")
        .map((zone) => (
          <CircleMarker
            key={`pulse-${zone.id}`}
            center={[zone.centroid_lat, zone.centroid_lng]}
            radius={6}
            pathOptions={{ color: STATUS_COLOR.severe, fillColor: STATUS_COLOR.severe, fillOpacity: 0.9 }}
          />
        ))}
    </MapContainer>
  );
}
