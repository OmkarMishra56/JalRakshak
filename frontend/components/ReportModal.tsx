"use client";
/**
 * One-tap "report waterlogging here" flow: auto-geolocation, a depth slider
 * (with plain-language landmarks: ankle/knee/waist/chest), optional note.
 */
import { useState } from "react";
import { api } from "@/lib/api";

const DEPTH_LANDMARKS = [
  { max: 5, label: "Damp / puddling" },
  { max: 15, label: "Ankle-deep" },
  { max: 45, label: "Knee-deep" },
  { max: 80, label: "Waist-deep" },
  { max: 300, label: "Chest-deep or higher" },
];

function landmarkFor(cm: number) {
  return DEPTH_LANDMARKS.find((l) => cm <= l.max)?.label ?? "Severe";
}

export default function ReportModal({ onClose, onSubmitted }: { onClose: () => void; onSubmitted: () => void }) {
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [locating, setLocating] = useState(true);
  const [locError, setLocError] = useState<string | null>(null);
  const [depth, setDepth] = useState(20);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useState(() => {
    if (!navigator.geolocation) {
      setLocError("Geolocation not supported on this device.");
      setLocating(false);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setLocating(false);
      },
      () => {
        setLocError("Couldn't get your location. Enable location access and try again.");
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  });

  async function submit() {
    if (!coords) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.createReport({ lat: coords.lat, lng: coords.lng, water_depth_cm: depth, note: note || undefined });
      onSubmitted();
    } catch (e: any) {
      setError(e.message || "Couldn't submit report.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[1000] flex items-end sm:items-center justify-center bg-black/60">
      <div className="bg-panel border border-line rounded-t-2xl sm:rounded-2xl w-full sm:w-[420px] p-5 shadow-panel">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display text-lg text-foam">Report waterlogging</h3>
          <button onClick={onClose} className="text-mist hover:text-foam text-xl leading-none px-2">×</button>
        </div>

        {locating && <div className="text-sm text-mist mb-4">Finding your location…</div>}
        {locError && <div className="text-sm text-severe mb-4">{locError}</div>}
        {coords && (
          <div className="text-xs font-mono text-mist mb-4">
            {coords.lat.toFixed(5)}, {coords.lng.toFixed(5)}
          </div>
        )}

        <div className="mb-5">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-mist">Water depth</span>
            <span className="text-foam font-mono">{depth} cm — {landmarkFor(depth)}</span>
          </div>
          <input
            type="range"
            min={0}
            max={150}
            value={depth}
            onChange={(e) => setDepth(Number(e.target.value))}
            className="w-full accent-tide"
          />
        </div>

        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Optional: what are you seeing? (e.g. 'cars stalling', 'road fully blocked')"
          maxLength={500}
          className="w-full bg-panel2 border border-line rounded-lg p-3 text-sm text-foam placeholder:text-mist mb-4 resize-none h-20"
        />

        {error && <div className="text-sm text-severe mb-3">{error}</div>}

        <button
          onClick={submit}
          disabled={!coords || submitting}
          className="w-full bg-tide text-ink font-semibold rounded-lg py-3 disabled:opacity-40 transition"
        >
          {submitting ? "Submitting…" : "Submit report"}
        </button>
      </div>
    </div>
  );
}
