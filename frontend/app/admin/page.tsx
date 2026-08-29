"use client";

import { useEffect, useState } from "react";
import { api, API_URL, Report } from "@/lib/api";

function useToken() {
  const [token, setToken] = useState<string | null>(null);
  useEffect(() => {
    setToken(typeof window !== "undefined" ? window.localStorage.getItem("aquaalert_token") : null);
  }, []);
  return [token, setToken] as const;
}

function LoginForm({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [email, setEmail] = useState("admin@demo.aquaalert.io");
  const [password, setPassword] = useState("password123");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.login(email, password);
      window.localStorage.setItem("aquaalert_token", res.access_token);
      onLoggedIn();
    } catch (e: any) {
      setError(e.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-24 bg-panel border border-line rounded-2xl p-6">
      <h1 className="font-display text-xl text-foam mb-1">Municipal login</h1>
      <p className="text-mist text-sm mb-5">Demo account is pre-filled — just sign in.</p>
      <input
        className="w-full bg-panel2 border border-line rounded-lg p-3 text-sm text-foam mb-3"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email"
      />
      <input
        className="w-full bg-panel2 border border-line rounded-lg p-3 text-sm text-foam mb-4"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
      />
      {error && <div className="text-severe text-sm mb-3">{error}</div>}
      <button
        onClick={submit}
        disabled={busy}
        className="w-full bg-tide text-ink font-semibold rounded-lg py-3 disabled:opacity-40"
      >
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-panel2 border border-line rounded-lg p-4">
      <div className="text-mist text-xs uppercase tracking-wider">{label}</div>
      <div className="text-2xl font-mono text-foam mt-1">{value}</div>
    </div>
  );
}

function Dashboard() {
  const [summary, setSummary] = useState<any>(null);
  const [pending, setPending] = useState<Report[]>([]);
  const [analytics, setAnalytics] = useState<any[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  function refresh() {
    api.dashboardSummary().then(setSummary).catch(() => {});
    api.pendingReports().then(setPending).catch(() => {});
    api.analytics().then(setAnalytics).catch(() => {});
  }

  useEffect(refresh, []);

  async function moderate(id: string, action: "verify" | "dismiss") {
    setBusyId(id);
    try {
      await api.moderateReport(id, action);
      refresh();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="max-w-5xl mx-auto py-8 px-4 space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl text-foam">Municipal Dashboard</h1>
        <a
          href={`${API_URL}/admin/export/reports.csv`}
          className="text-xs font-mono border border-line rounded-full px-4 py-2 text-mist hover:text-foam"
        >
          Export reports CSV ↓
        </a>
      </div>

      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard label="Severe zones" value={summary.severe_zones} />
          <StatCard label="Moderate zones" value={summary.moderate_zones} />
          <StatCard label="Safe zones" value={summary.safe_zones} />
          <StatCard label="Pending reports" value={summary.pending_reports} />
        </div>
      )}

      <section>
        <h2 className="text-mist text-xs uppercase tracking-wider mb-3">Moderation queue</h2>
        {pending.length === 0 && <div className="text-mist text-sm">No reports awaiting review.</div>}
        <div className="space-y-2">
          {pending.map((r) => (
            <div key={r.id} className="bg-panel2 border border-line rounded-lg p-4 flex items-center justify-between gap-4">
              <div className="text-sm">
                <div className="font-mono text-foam">{r.water_depth_cm.toFixed(0)} cm deep</div>
                <div className="text-mist text-xs">{r.lat.toFixed(4)}, {r.lng.toFixed(4)} · {new Date(r.created_at).toLocaleString()}</div>
                {r.note && <div className="text-mist text-sm mt-1">{r.note}</div>}
              </div>
              <div className="flex gap-2 shrink-0">
                <button
                  disabled={busyId === r.id}
                  onClick={() => moderate(r.id, "verify")}
                  className="text-xs bg-tide text-ink font-semibold rounded-full px-3 py-1.5 disabled:opacity-40"
                >
                  Verify
                </button>
                <button
                  disabled={busyId === r.id}
                  onClick={() => moderate(r.id, "dismiss")}
                  className="text-xs border border-line text-mist rounded-full px-3 py-1.5 disabled:opacity-40"
                >
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-mist text-xs uppercase tracking-wider mb-3">Which zones flood most (30d)</h2>
        <div className="bg-panel2 border border-line rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-mist text-xs border-b border-line">
                <th className="p-3">Zone</th>
                <th className="p-3">Avg score</th>
                <th className="p-3">Max score</th>
                <th className="p-3">Severe incidents</th>
                <th className="p-3">Reports</th>
              </tr>
            </thead>
            <tbody>
              {analytics.map((a) => (
                <tr key={a.zone_id} className="border-b border-line last:border-0">
                  <td className="p-3 text-foam">{a.name} <span className="text-mist text-xs">({a.code})</span></td>
                  <td className="p-3 font-mono text-foam">{a.avg_score_30d}</td>
                  <td className="p-3 font-mono text-foam">{a.max_score_30d}</td>
                  <td className="p-3 font-mono text-severe">{a.severe_incidents_30d}</td>
                  <td className="p-3 font-mono text-foam">{a.total_reports_30d}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

export default function AdminPage() {
  const [token, setToken] = useToken();
  if (token === null) return <LoginForm onLoggedIn={() => setToken(window.localStorage.getItem("aquaalert_token"))} />;
  return <Dashboard />;
}
