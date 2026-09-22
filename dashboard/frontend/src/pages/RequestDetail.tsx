import { JsonBlock, RailBars, SourceTag, StatusPill, formatTs } from "../components";
import type { RequestRecord } from "../types";

export default function RequestDetail({ record }: { record: RequestRecord }) {
  return (
    <div style={{ border: "1px solid #dadce0", borderRadius: 8, padding: 16, marginTop: 16 }}>
      <h3 style={{ marginTop: 0 }}>
        Request detail <StatusPill status={record.status} /> <SourceTag source={record.source} />
      </h3>
      <p style={{ fontSize: 13, color: "#5f6368" }}>
        {formatTs(record.ts)} — config: {record.config_id ?? "n/a"} — thread: {record.thread_id ?? "n/a"}
        {record.interaction_id ? ` — interaction: ${record.interaction_id}` : ""}
      </p>
      {record.error && <p style={{ color: "#b3261e" }}>Error: {record.error}</p>}
      <h4>Activated rails</h4>
      <RailBars rails={record.rails} />
      <h4>LLM calls</h4>
      {record.llm_calls.length ? (
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #dadce0" }}>
              <th>Task</th><th>Model</th><th>Prompt tok</th><th>Completion tok</th><th>Total</th><th>Duration</th><th>Cache</th>
            </tr>
          </thead>
          <tbody>
            {record.llm_calls.map((c, i) => (
              <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
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
          <h4>Phase durations</h4>
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
      <h4>Raw request</h4>
      <JsonBlock data={record.raw_request} />
      <h4>Raw response</h4>
      <JsonBlock data={record.raw_response} />
    </div>
  );
}
