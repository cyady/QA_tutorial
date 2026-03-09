import type { RunDetail, RunsResponse } from "./types";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`request failed (${response.status}) ${url}: ${text}`);
  }
  return (await response.json()) as T;
}

export function fetchRuns(limit = 300): Promise<RunsResponse> {
  return fetchJson<RunsResponse>(`/api/runs?limit=${limit}`);
}

export function fetchRunDetail(runId: string): Promise<RunDetail> {
  return fetchJson<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`);
}
