
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = window.localStorage.getItem("aquaalert_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export interface ZoneGeoJSON {
  type: "Polygon";
  coordinates: number[][][];
}

export interface Zone {
  id: string;
  name: string;
  code: string;
  centroid_lat: number;
  centroid_lng: number;
  current_score: number;
  current_status: "safe" | "moderate" | "severe";
  score_updated_at: string;
  geojson: ZoneGeoJSON;
}

export interface Report {
  id: string;
  zone_id: string;
  lat: number;
  lng: number;
  water_depth_cm: number;
  photo_url?: string | null;
  note?: string | null;
  is_verified: boolean;
  is_municipal_override: boolean;
  is_dismissed: boolean;
  created_at: string;
}

export interface ZoneDetail extends Zone {
  recent_reports: Report[];
  rainfall_1h_mm: number;
  rainfall_24h_mm: number;
  historical_flood_prior: number;
}

export const api = {
  listZones: () => request<Zone[]>("/zones"),
  zoneDetail: (id: string) => request<ZoneDetail>(`/zones/${id}`),
  zoneHistory: (id: string, hours = 24) =>
    request<{ score: number; status: string; recorded_at: string; rainfall_component: number }[]>(
      `/zones/${id}/history?hours=${hours}`
    ),
  floodProneZones: () => request<Zone[]>("/zones/lookup/flood-prone"),

  createReport: (payload: {
    lat: number;
    lng: number;
    water_depth_cm: number;
    note?: string;
    photo_url?: string;
  }) => request<Report>("/reports", { method: "POST", body: JSON.stringify(payload) }),

  login: (email: string, password: string) =>
    request<{ access_token: string; user: any }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (payload: { email: string; password: string; full_name?: string; role?: string }) =>
    request<{ access_token: string; user: any }>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  pendingReports: () => request<Report[]>("/admin/reports/pending"),
  moderateReport: (id: string, action: "verify" | "dismiss") =>
    request<Report>(`/reports/${id}/moderate`, { method: "PATCH", body: JSON.stringify({ action }) }),
  dashboardSummary: () => request<any>("/admin/dashboard-summary"),
  analytics: () => request<any[]>("/admin/analytics"),

  suggestRoute: (startZoneId: string, endZoneId: string) =>
    request<any>(`/routes/suggest?start_zone_id=${startZoneId}&end_zone_id=${endZoneId}`),
};
