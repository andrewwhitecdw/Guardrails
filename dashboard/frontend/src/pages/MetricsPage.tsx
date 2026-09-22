import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api } from "../api";
import type { MetricSample } from "../types";

export default function MetricsPage() {
  const [samples, setSamples] = useState<MetricSample[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const data = await api.series("guardrails_nonstream");
        if (alive) {
          setSamples(data);
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
      <h1>Metrics</h1>
      <p style={{ fontSize: 13, color: "#9d9d9d" }}>
        Time series scraped from the guardrails Prometheus exporter. Shows the
        exported admission-queue instruments (refreshes every 5 seconds).
      </p>
      {error && <p style={{ color: "#ff5c5c" }}>{error}</p>}
      {!error && samples.length === 0 && (
        <em>
          No samples yet. Start the dashboard with --prom-url pointing at the
          guardrails metrics exporter and generate some traffic.
        </em>
      )}
      {series.map((s) => (
        <div key={s.name} style={{ marginBottom: 32 }}>
          <h3 style={{ fontSize: 14 }}>{s.name}</h3>
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer>
              <LineChart data={s.points}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="value" dot={false} stroke="#76b900" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ))}
    </div>
  );
}
