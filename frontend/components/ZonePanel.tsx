"use client";
import { useEffect, useState } from "react";
import { api, ZoneDetail } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  safe: "#22C55E",
  moderate: "#F5B93D",
  severe: "#EF4444",
};

export default function ZonePanel({ zoneId, onClose }: { zoneId: string; onClose: () => void }) {
  const [detail, setDetail] = useState<ZoneDetail | null>(null);
  const [history, setHistory] = useState<{ score: number; recorded_at: string }[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([api.zoneDetail(zoneId), api.zoneHistory(zoneId, 24)])
      .then(([d, h]) => {
        if (cancelled) return;
        setDetail(d);
        setHistory(h);
      })
      .catch(() => {})
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [zoneId]);

  const sparkPoints = history.length
    ? history
        .map((h, i) => {
          const x = (i / Math.max(1, history.length - 1)) * 100;
          const y = 40 - (h.score / 100) * 36;
          return `${x},${y}`;
        })
        .join(" ")
    : "";

  return (
    <div className="absolute top-0 right-0 h-full w-full sm:w-[380px] bg-panel border-l border-line shadow-panel z-[500] overflow-y-auto">
      <div className="flex items-center justify-between px-5 py-4 border-b border-line sticky top-0 bg-panel/95 backdrop-blur">
        <div>
          <div className="text-xs text-mist font-mono uppercase tracking-wider">
            {detail?.code ?? "…"}
          </div>
          <h2 className="text-lg font-display text-foam">{detail?.name ?? "Loading…"}</h2>
        </div>
        <button onClick={onClose} className="text-mist hover:text-foam text-xl leading-none px-2">
          ×
        </button>
      </div>

      {loading || !detail ? (
        <div className="p-5 text-mist text-sm">Loading zone data…</div>
      ) : (
        <div className="p-5 space-y-6">
          <div className="flex items-center gap-3">
            <span
              className="inline-block w-3 h-3 rounded-full"
              style={{ backgroundColor: STATUS_COLOR[detail.current_status] }}
            />
            <span className="text-2xl font-mono text-foam">{detail.current_score.toFixed(0)}</span>
            <span className="text-mist text-sm">/ 100 · {detail.current_status}</span>
          </div>

          <div>
            <div className="text-xs text-mist uppercase tracking-wider mb-2">24h trend</div>
            <svg viewBox="0 0 100 40" className="w-full h-16">
              <polyline
                points={sparkPoints}
                fill="none"
                stroke="#2DD4BF"
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
            {!history.length && <div className="text-xs text-mist">No history yet for this zone.</div>}
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-panel2 rounded-lg p-3 border border-line">
              <div className="text-mist text-xs">Rainfall (1h)</div>
              <div className="font-mono text-foam text-lg">{detail.rainfall_1h_mm.toFixed(1)} mm</div>
            </div>
            <div className="bg-panel2 rounded-lg p-3 border border-line">
              <div className="text-mist text-xs">Rainfall (24h)</div>
              <div className="font-mono text-foam text-lg">{detail.rainfall_24h_mm.toFixed(1)} mm</div>
            </div>
            <div className="bg-panel2 rounded-lg p-3 border border-line col-span-2">
              <div className="text-mist text-xs">Historical flood tendency</div>
              <div className="font-mono text-foam text-lg">{detail.historical_flood_prior.toFixed(0)} / 100</div>
            </div>
          </div>

          <div>
            <div className="text-xs text-mist uppercase tracking-wider mb-2">
              Recent reports ({detail.recent_reports.length})
            </div>
            {detail.recent_reports.length === 0 && (
              <div className="text-sm text-mist">No reports in the last 6 hours — score reflects weather + history only.</div>
            )}
            <div className="space-y-2">
              {detail.recent_reports.map((r) => (
                <div key={r.id} className="bg-panel2 rounded-lg p-3 border border-line text-sm">
                  <div className="flex justify-between items-center">
                    <span className="font-mono text-foam">{r.water_depth_cm.toFixed(0)} cm</span>
                    <span className="text-xs text-mist">{new Date(r.created_at).toLocaleTimeString()}</span>
                  </div>
                  {r.note && <div className="text-mist mt-1">{r.note}</div>}
                  {r.is_verified && <div className="text-tide text-xs mt-1">✓ Verified by municipal admin</div>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
