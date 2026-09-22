import { useEffect, useState } from "react";

import { api } from "../api";

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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .telemetryEvents()
      .then((d) => setEvents(d.items))
      .catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div>
      <h1>Telemetry</h1>
      <p style={{ fontSize: 13, color: "#5f6368" }}>
        Anonymous usage events from the local audit file
        (~/.config/nemoguardrails/usage_stats.json). Read-only; newest last.
      </p>
      {error && <p style={{ color: "#b3261e" }}>{error}</p>}
      {events.length === 0 && !error && <em>No telemetry events found.</em>}
      {events.length > 0 && (
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "2px solid #dadce0" }}>
              {COLUMNS.map((c) => (
                <th key={c}>{c}</th>
              ))}
              <th>railTypesInUse</th>
              <th>llmProviders</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e, i) => (
              <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
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
      )}
    </div>
  );
}
