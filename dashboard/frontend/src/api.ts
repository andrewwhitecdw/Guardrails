import type {
  ChallengeRunResult,
  MetricSample,
  OverviewStats,
  RailFrequency,
  RecordsResponse,
  RequestRecord,
  StatusResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function qs(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  return search.toString();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: init?.body
      ? { "Content-Type": "application/json", ...init.headers }
      : init?.headers,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      // keep statusText
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });
}

export const api = {
  status: () => request<StatusResponse>("/api/status"),
  records: (params: Record<string, string | number | undefined>) =>
    request<RecordsResponse>(`/api/requests?${qs(params)}`),
  record: (id: string) => request<RequestRecord>(`/api/requests/${id}`),
  overview: (start?: number, end?: number) =>
    request<OverviewStats>(`/api/metrics/overview?${qs({ start, end })}`),
  rails: () => request<RailFrequency[]>("/api/metrics/rails"),
  series: (namePrefix: string) =>
    request<MetricSample[]>(`/api/metrics/series?${qs({ name_prefix: namePrefix })}`),
  telemetryEvents: () => request<{ items: Record<string, unknown>[] }>("/api/telemetry/events"),
  consoleRun: (body: unknown) => post<unknown>("/api/commands/console/run", body),
  checksRun: (body: unknown) => post<unknown>("/api/commands/checks/run", body),
  challenges: () => request<{ items: Record<string, unknown>[] }>("/api/commands/challenges"),
  runChallenges: (body: unknown) =>
    post<{ results: ChallengeRunResult[] }>("/api/commands/challenges/run", body),
  adminCapabilities: () => request<{ installed: boolean }>("/api/commands/admin/capabilities"),
  adminReload: (configId?: string) =>
    post<unknown>("/api/commands/admin/reload", { config_id: configId }),
};

export function extractSseText(sse: string): string {
  let out = "";
  for (const event of sse.split("\n\n")) {
    for (const line of event.split("\n")) {
      if (!line.startsWith("data:")) continue;
      const payload = line.slice("data:".length).trim();
      if (!payload || payload === "[DONE]") continue;
      try {
        const chunk = JSON.parse(payload);
        for (const choice of chunk.choices ?? []) {
          out += choice.delta?.content ?? "";
        }
      } catch {
        // ignore non-JSON keepalives
      }
    }
  }
  return out;
}
