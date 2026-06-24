import type {
  BrowseItem,
  BrowseFilters,
  DashboardPayload,
  PaginatedResponse,
  ProfilesResponse,
  ApifyAlert,
  AuthUser,
} from "./types";
import { proxyUrl } from "./utils";

export async function djFetchRaw(path: string, init?: RequestInit): Promise<Response> {
  const url = proxyUrl(path);
  const res = await fetch(url, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers as Record<string, string>),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text.slice(0, 200)}`);
  }
  return res;
}

async function djFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await djFetchRaw(path, init);
  return res.json() as Promise<T>;
}

// ── Browse ────────────────────────────────────────────────────────────────

export async function fetchBrowsePage(
  filters: BrowseFilters,
  page: number,
  pageSize = 25
): Promise<PaginatedResponse<BrowseItem>> {
  const p = new URLSearchParams();
  if (filters.profileId) p.set("profile_id", filters.profileId);
  if (filters.tiers.length) p.set("tiers", filters.tiers.join(","));
  if (filters.source) p.set("source", filters.source);
  if (filters.language) p.set("language", filters.language);
  if (filters.location) p.set("location", filters.location);
  if (filters.remote) p.set("remote", filters.remote);
  if (filters.applied) p.set("applied", filters.applied);
  p.set("date", filters.date);
  if (filters.q) p.set("q", filters.q);
  p.set("page", String(page));
  p.set("page_size", String(pageSize));
  return djFetch<PaginatedResponse<BrowseItem>>(`/browse/?${p.toString()}`);
}

export async function fetchJobDetail(jobId: number) {
  return djFetch<Record<string, unknown>>(`/jobs/${jobId}/`);
}

export async function patchJob(
  jobId: number,
  data: { is_applied?: boolean }
) {
  return djFetch(`/jobs/${jobId}/`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

// ── Rankings ──────────────────────────────────────────────────────────────

export async function patchRanking(
  rankingId: number,
  data: { match_tier?: string; rank?: number }
) {
  return djFetch(`/rankings/${rankingId}/`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

// ── Profiles + choices ────────────────────────────────────────────────────

export async function fetchProfiles(): Promise<ProfilesResponse> {
  return djFetch<ProfilesResponse>("/profiles/");
}

// ── Dashboard / insights ──────────────────────────────────────────────────

export async function fetchDashboard(profileId: string): Promise<DashboardPayload> {
  return djFetch<DashboardPayload>(`/dashboard/?profile_id=${encodeURIComponent(profileId)}`);
}

export async function fetchDashboardAlert(): Promise<{ alert: ApifyAlert | null }> {
  return djFetch<{ alert: ApifyAlert | null }>("/dashboard/alert/");
}

// ── Pipeline actions ──────────────────────────────────────────────────────

export async function triggerScrape(source?: string) {
  return djFetch("/pipeline/trigger-scrape/", {
    method: "POST",
    body: JSON.stringify({ source: source || "" }),
  });
}

export async function triggerProcessing() {
  return djFetch("/pipeline/trigger-processing/", { method: "POST" });
}

// ── Auth ──────────────────────────────────────────────────────────────────

export async function fetchMe(): Promise<AuthUser> {
  return djFetch<AuthUser>("/auth/me/");
}

export async function login(username: string, password: string): Promise<AuthUser> {
  return djFetch<AuthUser>("/auth/login/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function logout(): Promise<void> {
  await djFetch("/auth/logout/", { method: "POST" });
}

// ── Settings (admin only) ─────────────────────────────────────────────────

export interface AppSettings {
  OPENAI_BASE_URL: string;
  OPENAI_MODEL: string;
  APIFY_API_TOKEN: string;
  OPENAI_API_KEYS: string[];
}

export async function fetchSettings(): Promise<AppSettings> {
  return djFetch<AppSettings>("/auth/settings/");
}

export async function saveSettings(data: Partial<AppSettings>): Promise<{ status: string; message: string }> {
  return djFetch("/auth/settings/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}
