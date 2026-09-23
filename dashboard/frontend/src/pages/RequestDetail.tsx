import { JsonBlock, RailBars, SourceTag, StatusPill, formatTs } from "../components";
import { Card } from "../ui";
import { colors } from "../theme";
import type { RequestRecord } from "../types";

export default function RequestDetail({ record }: { record: RequestRecord }) {
  return (
    <Card
      title="Request detail"
      actions={
        <span style={{ display: "flex", gap: 6 }}>
          <StatusPill status={record.status} />
          <SourceTag source={record.source} />
        </span>
      }
      style={{ marginTop: 16 }}
    >
      <p style={{ fontSize: 13, color: colors.muted, marginTop: 0 }}>
        {formatTs(record.ts)} — config: {record.config_id ?? "n/a"} — thread: {record.thread_id ?? "n/a"}
        {record.interaction_id ? ` — interaction: ${record.interaction_id}` : ""}
      </p>
      {record.error && <p style={{ color: colors.red }}>Error: {record.error}</p>}
      <h4 style={{ color: colors.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 1 }}>Activated rails</h4>
      <RailBars rails={record.rails} />
      <h4 style={{ color: colors.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 1 }}>LLM calls</h4>
      {record.llm_calls.length ? (
        <table className="nv-table">
          <thead>
            <tr>
              <th>Task</th><th>Model</th><th>Prompt tok</th><th>Completion tok</th><th>Total</th><th>Duration</th><th>Cache</th>
            </tr>
          </thead>
          <tbody>
            {record.llm_calls.map((c, i) => (
              <tr key={i}>
                <td>{c.task ?? ""}</td>
                <td>{c.model ?? "unknown"}</td>
                <td>{c.prompt_tokens ?? ""}</td>
                <td>{c.completion_tokens ?? ""}</td>
                <td>{c.total_tokens ?? ""}</td>
                <td>{c.duration != null ? `${Math.round(c.duration * 1000)} ms` : ""}</td>
                <td>{c.from_cache ? "hit" : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <em>No LLM calls captured.</em>
      )}
      {Object.keys(record.phase_durations).length > 0 && (
        <>
          <h4 style={{ color: colors.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 1 }}>Phase durations</h4>
          <ul>
            {Object.entries(record.phase_durations).map(([k, v]) => (
              <li key={k}>
                {k}: {v == null
                  ? "n/a"
                  : k.endsWith("_duration") && typeof v === "number"
                    ? `${Math.round(v * 1000)} ms`
                    : String(v)}
              </li>
            ))}
          </ul>
        </>
      )}
      <h4 style={{ color: colors.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 1 }}>Raw request</h4>
      <JsonBlock data={record.raw_request} />
      <h4 style={{ color: colors.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 1 }}>Raw response</h4>
      <JsonBlock data={record.raw_response} />
    </Card>
  );
}
