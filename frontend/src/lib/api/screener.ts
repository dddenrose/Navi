// Screener API client
import { getAuthHeaders } from "@/lib/api";
import type {
  ReportSummary,
  ReportDetail,
  ScreenerProfile,
  ScreenerFrequency,
  EmailSubscription,
  TrackingSummary,
} from "@/types/screener";

const BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  "https://navi-backend-58156810941.asia-east1.run.app";

async function authedFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (!res.ok) throw new Error(await res.text());
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export async function listReports(params?: {
  profile?: ScreenerProfile;
  frequency?: ScreenerFrequency;
  limit?: number;
}): Promise<ReportSummary[]> {
  const q = new URLSearchParams();
  if (params?.profile) q.set("profile", params.profile);
  if (params?.frequency) q.set("frequency", params.frequency);
  if (params?.limit) q.set("limit", String(params.limit));
  const suffix = q.toString() ? `?${q.toString()}` : "";
  return authedFetch<ReportSummary[]>(`/api/screener/reports${suffix}`);
}

export async function getLatestReport(
  profile: ScreenerProfile = "momentum",
  frequency: ScreenerFrequency = "weekly",
): Promise<ReportDetail> {
  return authedFetch<ReportDetail>(
    `/api/screener/reports/latest?profile=${profile}&frequency=${frequency}`,
  );
}

export async function getReport(reportId: string): Promise<ReportDetail> {
  return authedFetch<ReportDetail>(`/api/screener/reports/${reportId}`);
}

export async function getTrackingSummary(
  profile: ScreenerProfile,
): Promise<TrackingSummary | null> {
  // 尚未累積統計時後端回 404 — 面板隱藏即可，不當錯誤處理
  try {
    return await authedFetch<TrackingSummary>(
      `/api/screener/tracking/summary?profile=${profile}`,
    );
  } catch {
    return null;
  }
}

export async function getSubscription(): Promise<EmailSubscription> {
  return authedFetch<EmailSubscription>(`/api/screener/subscriptions`);
}

export async function updateSubscription(
  payload: Partial<Omit<EmailSubscription, "user_id" | "updated_at">>,
): Promise<EmailSubscription> {
  return authedFetch<EmailSubscription>(`/api/screener/subscriptions`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}
