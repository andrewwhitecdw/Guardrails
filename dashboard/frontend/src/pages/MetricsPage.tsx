import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "../api";
import { Card, EmptyState, Skeleton } from "../ui";
import { colors } from "../theme";
import type { MetricSample } from "../types";

const tooltipStyle = {
  backgroundColor: colors.panel,
  border: `1px solid ${colors.panelBorder}`,
  borderRadius: 8,
  fontSize: 12,
} as const;

export default function MetricsPage() {
  const [samples, setSamples] = useState<MetricSample[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const data = await api.series("guardrails_nonstream");
        if (alive) {
          setSamples(data);
          setError(null);
          setLoaded(true);
        }
      } catch (e) {
        if (alive) {
          setError((e as Error).message);
          setLoaded(true);
        }
      }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  // one series per (metric name + label signature)
  const series = useMemo(() => {
    const groups = new Map<string, MetricSample[]>();
    for (const s of samples) {
      const labelSig = Object.entries(s.labels)
        .map(([k, v]) => `${k}=${v}`)
        .join(",");
      const key = labelSig ? `${s.name}{${labelSig}}` : s.name;
      const list = groups.get(key) ?? [];
      list.push(s);
      groups.set(key, list);
    }
    return [...groups.entries()].map(([name, points]) => ({
      name,
      points: points.map((p) => ({ time: new Date(p.ts).toLocaleTimeString(), value: p.value })),
    }));
  }, [samples]);

  return (
    <div>
      <p style={{ fontSize: 13, color: colors.muted, marginTop: 0 }}>
        Time series scraped from the guardrails Prometheus exporter. Shows the
        exported admission-queue instruments (refreshes every 5 seconds).
      </p>
      {error && <p style={{ color: colors.red }}>{error}</p>}
      {!loaded && <Skeleton height={220} />}
      {loaded && !error && samples.length === 0 && (
        <Card>
          <EmptyState
            title="No samples yet"
            hint="Start the dashboard with --prom-url pointing at the guardrails metrics exporter and generate some traffic."
          />
        </Card>
      )}
      {series.map((s) => (
        <Card key={s.name} title={<span style={{ fontFamily: "monospace", fontSize: 13 }}>{s.name}</span>} style={{ marginBottom: 16 }}>
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer>
              <LineChart data={s.points}>
                <CartesianGrid stroke="#1f1f1f" strokeDasharray="3 3" />
                <XAxis dataKey="time" stroke={colors.muted} tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} stroke={colors.muted} tick={{ fontSize: 11 }} />
                <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: colors.muted }} />
                <Legend />
                <Line type="monotone" dataKey="value" dot={false} stroke={colors.green} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      ))}
    </div>
  );
}
