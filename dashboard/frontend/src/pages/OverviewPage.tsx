import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { usePageActions } from "../App";
import { api } from "../api";
import { formatMs } from "../components";
import { Card, Skeleton } from "../ui";
import { cardStyle, colors } from "../theme";
import type { OverviewStats, StatusResponse } from "../types";

const RANGES: [string, number][] = [
  ["15 minutes", 15 * 60 * 1000],
  ["1 hour", 60 * 60 * 1000],
  ["24 hours", 24 * 60 * 60 * 1000],
];

const tooltipStyle = {
  backgroundColor: colors.panel,
  border: `1px solid ${colors.panelBorder}`,
  borderRadius: 8,
  fontSize: 12,
} as const;

export default function OverviewPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [rangeMs, setRangeMs] = useState(RANGES[0][1]);
  const [error, setError] = useState<string | null>(null);
  const setActions = usePageActions();

  useEffect(() => {
    setActions(
      <select
        value={rangeMs}
        onChange={(e) => setRangeMs(Number(e.target.value))}
        aria-label="Time range"
      >
        {RANGES.map(([label, ms]) => (
          <option key={label} value={ms}>
            {label}
          </option>
        ))}
      </select>,
    );
    return () => setActions(null);
  }, [rangeMs, setActions]);

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
      {error && <p style={{ color: colors.red }}>{error}</p>}
      {status && (
        <p style={{ marginTop: 0, color: colors.muted, fontSize: 13 }}>
          Guardrails server{" "}
          <strong style={{ color: healthy ? colors.green : colors.red }}>
            {healthy ? "healthy" : "unreachable"}
          </strong>{" "}
          ({status.guardrails.url}) — admin hook{" "}
          {status.admin_hook ? (
            <span style={{ color: colors.green }}>installed</span>
          ) : (
            <span style={{ color: colors.amber }}>not installed</span>
          )}
        </p>
      )}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
        {stats ? (
          <>
            <StatCard label="Requests" value={stats.count} />
            <StatCard label="Blocked" value={stats.blocked} />
            <StatCard label="Errors" value={stats.errors} />
            <StatCard label="p50 latency" value={formatMs(stats.p50_ms)} />
            <StatCard label="p95 latency" value={formatMs(stats.p95_ms)} />
            <StatCard label="Input tokens" value={stats.input_tokens} />
            <StatCard label="Output tokens" value={stats.output_tokens} />
          </>
        ) : (
          Array.from({ length: 7 }, (_, i) => (
            <Skeleton key={i} width={130} height={64} />
          ))
        )}
      </div>
      <Card title="Requests over selected range">
        <div style={{ width: "100%", height: 260 }}>
          <ResponsiveContainer>
            <AreaChart data={chartData}>
              <CartesianGrid stroke="#1f1f1f" strokeDasharray="3 3" />
              <XAxis dataKey="time" stroke={colors.muted} tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} stroke={colors.muted} tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: colors.muted }} />
              <Area
                type="monotone"
                dataKey="requests"
                name="requests"
                stroke={colors.green}
                fill={colors.green}
                fillOpacity={0.2}
              />
              <Area
                type="monotone"
                dataKey="blocked"
                name="blocked"
                stroke={colors.red}
                fill={colors.red}
                fillOpacity={0.3}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>
      {status && (
        <Card title="Ingestion" style={{ marginTop: 20 }}>
          <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, fontSize: 13 }}>
            <div>
              <dt style={{ color: colors.muted, fontSize: 12 }}>Trace globs</dt>
              <dd style={{ margin: "2px 0 0" }}>{status.ingestion.trace_globs.join(", ") || "none"}</dd>
            </div>
            <div>
              <dt style={{ color: colors.muted, fontSize: 12 }}>Prometheus URL</dt>
              <dd style={{ margin: "2px 0 0" }}>{status.ingestion.prom_url || "none"}</dd>
            </div>
            <div>
              <dt style={{ color: colors.muted, fontSize: 12 }}>Records written</dt>
              <dd style={{ margin: "2px 0 0" }}>
                {status.ingestion.records_written} (duplicates skipped:{" "}
                {status.ingestion.records_dropped_duplicates})
              </dd>
            </div>
            <div>
              <dt style={{ color: colors.muted, fontSize: 12 }}>Malformed lines</dt>
              <dd style={{ margin: "2px 0 0" }}>
                {Object.entries(status.ingestion.malformed).length
                  ? Object.entries(status.ingestion.malformed)
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(", ")
                  : "none"}
              </dd>
            </div>
          </dl>
        </Card>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value?: number | string | null }) {
  return (
    <div style={{ ...cardStyle, borderLeft: `3px solid ${colors.green}`, padding: "12px 16px", minWidth: 120, flex: "1 1 120px" }}>
      <div style={{ fontSize: 12, color: colors.muted }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 650 }}>{value ?? "n/a"}</div>
    </div>
  );
}
