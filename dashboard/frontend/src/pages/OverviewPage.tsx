import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api } from "../api";
import { formatMs } from "../components";
import type { OverviewStats, StatusResponse } from "../types";

const RANGES: [string, number][] = [
  ["15 minutes", 15 * 60 * 1000],
  ["1 hour", 60 * 60 * 1000],
  ["24 hours", 24 * 60 * 60 * 1000],
];

export default function OverviewPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [rangeMs, setRangeMs] = useState(RANGES[0][1]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const end = Date.now();
        const [s, o] = await Promise.all([
          api.status(),
          api.overview(end - rangeMs, end),
        ]);
        if (alive) {
          setStatus(s);
          setStats(o);
          setError(null);
        }
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [rangeMs]);

  const healthy = status?.guardrails.healthy;
  const chartData = (stats?.buckets ?? []).map((b) => ({
    time: new Date(b.ts).toLocaleTimeString(),
    requests: b.count,
    blocked: b.blocked,
  }));

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h1>Overview</h1>
        <label>
          Range:{" "}
          <select value={rangeMs} onChange={(e) => setRangeMs(Number(e.target.value))}>
            {RANGES.map(([label, ms]) => (
              <option key={label} value={ms}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <p style={{ color: "#b3261e" }}>{error}</p>}
      {status && (
        <p>
          Guardrails server:{" "}
          <strong style={{ color: healthy ? "#137333" : "#b3261e" }}>
            {healthy ? "healthy" : "unreachable"}
          </strong>{" "}
          ({status.guardrails.url}) — admin hook {status.admin_hook ? "installed" : "not installed"}
        </p>
      )}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
        <StatCard label="Requests" value={stats?.count} />
        <StatCard label="Blocked" value={stats?.blocked} />
        <StatCard label="Errors" value={stats?.errors} />
        <StatCard label="p50 latency" value={formatMs(stats?.p50_ms)} />
        <StatCard label="p95 latency" value={formatMs(stats?.p95_ms)} />
        <StatCard label="Input tokens" value={stats?.input_tokens} />
        <StatCard label="Output tokens" value={stats?.output_tokens} />
      </div>
      <h3>Requests over selected range</h3>
      <div style={{ width: "100%", height: 260 }}>
        <ResponsiveContainer>
          <AreaChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Area type="monotone" dataKey="requests" stroke="#1a73e8" fill="#1a73e8" fillOpacity={0.2} />
            <Area type="monotone" dataKey="blocked" stroke="#b3261e" fill="#b3261e" fillOpacity={0.3} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      {status && (
        <>
          <h3>Ingestion</h3>
          <ul>
            <li>Trace globs: {status.ingestion.trace_globs.join(", ") || "none"}</li>
            <li>Prometheus URL: {status.ingestion.prom_url || "none"}</li>
            <li>Records written: {status.ingestion.records_written} (duplicates skipped: {status.ingestion.records_dropped_duplicates})</li>
            <li>
              Malformed lines:{" "}
              {Object.entries(status.ingestion.malformed).length
                ? Object.entries(status.ingestion.malformed)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(", ")
                : "none"}
            </li>
          </ul>
        </>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value?: number | string | null }) {
  return (
    <div style={{ border: "1px solid #dadce0", borderRadius: 8, padding: "12px 20px", minWidth: 110 }}>
      <div style={{ fontSize: 12, color: "#5f6368" }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 600 }}>{value ?? "n/a"}</div>
    </div>
  );
}
