import { useEffect, useState } from "react";

import { api } from "../api";
import { Card, EmptyState, Skeleton } from "../ui";

const COLUMNS = [
  "event",
  "timestamp",
  "sessionId",
  "nemoguardrailsVersion",
  "railsEngine",
  "deploymentType",
  "numRailsConfigured",
  "numCustomFlows",
  "tracingEnabled",
  "streamingConfigured",
];

export default function TelemetryPage() {
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .telemetryEvents()
      .then((d) => {
        setEvents(d.items);
        setLoaded(true);
      })
      .catch((e) => {
        setError((e as Error).message);
        setLoaded(true);
      });
  }, []);

  return (
    <div>
      <p style={{ fontSize: 13, color: "#9d9d9d", marginTop: 0 }}>
        Anonymous usage events from the local audit file
        (~/.config/nemoguardrails/usage_stats.json). Read-only; newest last.
      </p>
      {error && <p style={{ color: "#ff5c5c" }}>{error}</p>}
      {!loaded && <Skeleton height={120} />}
      {loaded && events.length === 0 && !error && (
        <Card>
          <EmptyState title="No telemetry events found" hint="Events appear after guardrails runs locally." />
        </Card>
      )}
      {events.length > 0 && (
        <Card>
          <table className="nv-table">
            <thead>
              <tr>
                {COLUMNS.map((c) => (
                  <th key={c}>{c}</th>
                ))}
                <th>railTypesInUse</th>
                <th>llmProviders</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e, i) => (
                <tr key={i}>
                  {COLUMNS.map((c) => (
                    <td key={c}>
                      {c === "timestamp"
                        ? e[c] != null
                          ? new Date(Number(e[c]) * 1000).toLocaleString()
                          : ""
                        : String(e[c] ?? "")}
                    </td>
                  ))}
                  <td>{Array.isArray(e.railTypesInUse) ? (e.railTypesInUse as string[]).join(", ") : ""}</td>
                  <td>{Array.isArray(e.llmProviders) ? (e.llmProviders as string[]).join(", ") : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
