import { cardStyle, colors } from "./theme";
import type { RailInfo } from "./types";

export function StatusPill({ status }: { status: string }) {
  const background =
    status === "blocked" ? colors.red : status === "error" ? colors.amber : colors.green;
  return (
    <span
      style={{
        background,
        color: "#000000",
        borderRadius: 10,
        padding: "2px 10px",
        fontSize: 11,
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: 0.5,
      }}
    >
      {status}
    </span>
  );
}

export function SourceTag({ source }: { source: string }) {
  return (
    <span
      style={{
        color: colors.muted,
        fontSize: 11,
        border: `1px solid ${colors.panelBorder}`,
        borderRadius: 10,
        padding: "1px 8px",
        textTransform: "uppercase",
        letterSpacing: 0.5,
      }}
    >
      {source}
    </span>
  );
}

export function JsonBlock({ data }: { data: unknown }) {
  if (data === null || data === undefined) return <em>none</em>;
  return (
    <pre
      style={{
        ...cardStyle,
        background: "#141414",
        padding: 12,
        overflow: "auto",
        maxHeight: 320,
        fontSize: 12,
        margin: 0,
      }}
    >
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

export function RailBars({ rails }: { rails: RailInfo[] }) {
  if (!rails.length) return <em>No rails activated.</em>;
  const max = Math.max(0.001, ...rails.map((r) => r.duration ?? 0));
  return (
    <div>
      {rails.map((rail, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <span style={{ minWidth: 240, fontSize: 13 }}>
            {rail.name}
            {rail.stop ? " (stopped)" : ""}
            {rail.type ? ` [${rail.type}]` : ""}
          </span>
          <div
            style={{
              height: 12,
              background: rail.stop ? colors.red : colors.green,
              borderRadius: 3,
              width: `${Math.max(2, ((rail.duration ?? 0) / max) * 100)}%`,
            }}
          />
          <span style={{ fontSize: 12, color: colors.muted }}>
            {rail.duration != null ? `${Math.round(rail.duration * 1000)} ms` : "n/a"}
          </span>
        </div>
      ))}
    </div>
  );
}

export function formatTs(ts: number): string {
  return new Date(ts).toLocaleString();
}

export function formatMs(ms: number | null | undefined): string {
  return ms == null ? "n/a" : `${Math.round(ms)} ms`;
}
