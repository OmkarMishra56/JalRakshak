"use client";
/**
 * Main citizen-facing view: live map dashboard + one-tap report FAB.
 * MapContainer (Leaflet) needs `window`, so it's loaded client-side only via
 * next/dynamic with ssr:false.
 */
import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, Zone } from "@/lib/api";
import { useZoneUpdates, ZoneUpdateEvent } from "@/lib/ws";
import ZonePanel from "@/components/ZonePanel";
import ReportModal from "@/components/ReportModal";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

const STATUS_COLOR: Record<string, string> = {
  safe: "#22C55E",
  moderate: "#F5B93D",
  severe: "#EF4444",
};

export default function HomePage() {
  const [zones, setZones] = useState<Zone[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);
  const [showReportModal, setShowReportModal] = useState(false);
  const [connected, setConnected] = useState(false);

  const loadZones = useCallback(() => {
    api.listZones().then(setZones).catch(() => {}).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadZones();
  }, [loadZones]);

  // Patch just the one zone that changed, in place -- this is what gets the
  // map updating live with no reload and sub-5s propagation.
  useZoneUpdates((event: ZoneUpdateEvent) => {
    setConnected(true);
    setZones((prev) =>
      prev.map((z) =>
        z.id === event.zone_id ? { ...z, current_score: event.score, current_status: event.status } : z
      )
    );
  });

  const severeCount = zones.filter((z) => z.current_status === "severe").length;
  const moderateCount = zones.filter((z) => z.current_status === "moderate").length;

  const centerLat = zones.length ? zones.reduce((s, z) => s + z.centroid_lat, 0) / zones.length : 12.9716;
  const centerLng = zones.length ? zones.reduce((s, z) => s + z.centroid_lng, 0) / zones.length : 77.5946;

  return (
    <div className="h-screen w-screen relative flex flex-col">
      <header className="flex items-center justify-between px-5 py-3 border-b border-line bg-panel z-[600]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-tide/15 border border-tide/40 flex items-center justify-center">
            <span className="text-tide text-sm">◐</span>
          </div>
          <div>
            <div className="font-display text-foam text-lg leading-none">AquaAlert</div>
            <div className="text-[11px] text-mist font-mono">Rainpur · live flood risk</div>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-3 text-xs font-mono text-mist">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full" style={{ background: STATUS_COLOR.severe }} />
              {severeCount} severe
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full" style={{ background: STATUS_COLOR.moderate }} />
              {moderateCount} moderate
            </span>
            <span className="flex items-center gap-1">
              <span className={`w-2 h-2 rounded-full ${connected ? "bg-tide" : "bg-mist"}`} />
              {connected ? "live" : "connecting…"}
            </span>
          </div>
          <Link href="/admin" className="text-xs font-mono text-mist hover:text-foam border border-line rounded-full px-3 py-1.5">
            Municipal login
          </Link>
        </div>
      </header>

      <div className="relative flex-1">
        {loading ? (
          <div className="h-full flex items-center justify-center text-mist text-sm">Loading live map…</div>
        ) : (
          <MapView
            zones={zones}
            onSelectZone={setSelectedZoneId}
            selectedZoneId={selectedZoneId}
            centerLat={centerLat}
            centerLng={centerLng}
          />
        )}

        {selectedZoneId && <ZonePanel zoneId={selectedZoneId} onClose={() => setSelectedZoneId(null)} />}

        <button
          onClick={() => setShowReportModal(true)}
          className="absolute bottom-6 left-1/2 -translate-x-1/2 sm:left-auto sm:right-6 sm:translate-x-0 z-[500] bg-tide text-ink font-semibold rounded-full px-6 py-3.5 shadow-panel flex items-center gap-2"
        >
          <span className="text-lg leading-none">＋</span> Report waterlogging
        </button>

        <div className="absolute bottom-6 left-6 hidden sm:flex flex-col gap-1.5 bg-panel/90 backdrop-blur border border-line rounded-lg px-3 py-2.5 z-[500]">
          {(["safe", "moderate", "severe"] as const).map((s) => (
            <div key={s} className="flex items-center gap-2 text-xs text-mist font-mono">
              <span className="w-2.5 h-2.5 rounded-sm" style={{ background: STATUS_COLOR[s] }} />
              {s}
            </div>
          ))}
        </div>
      </div>

      {showReportModal && (
        <ReportModal
          onClose={() => setShowReportModal(false)}
          onSubmitted={() => {
            setShowReportModal(false);
            loadZones();
          }}
        />
      )}
    </div>
  );
}
