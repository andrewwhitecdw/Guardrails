import { useEffect, useState } from "react";

import { api } from "../api";
import { JsonBlock, StatusPill } from "../components";
import type { ChallengeRunResult } from "../types";

export default function ChallengesPage() {
  const [configs, setConfigs] = useState<{ id: string }[]>([]);
  const [configId, setConfigId] = useState("");
  const [challenges, setChallenges] = useState<Record<string, unknown>[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [results, setResults] = useState<ChallengeRunResult[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.status(), api.challenges()])
      .then(([s, c]) => {
        setConfigs(s.guardrails.configs ?? []);
        if (s.guardrails.configs?.length) setConfigId(s.guardrails.configs[0].id);
        setChallenges(c.items);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  const toggle = (i: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      const ids = [...selected].map((i) => challenges[i]).map((c: any) => c.id).filter(Boolean);
      const data = await api.runChallenges({ config_id: configId || undefined, challenge_ids: ids });
      setResults(data.results);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const wasBlocked = (r: ChallengeRunResult) =>
    Boolean(r.response?.guardrails?.log?.activated_rails?.some((rail: any) => rail.stop));

  return (
    <div>
      <h1>Challenges</h1>
      <p style={{ fontSize: 13, color: "#5f6368" }}>
        Red-teaming challenge prompts served by the guardrails server
        (/v1/challenges). Runs are recorded with source=challenge.
      </p>
      {error && <p style={{ color: "#b3261e" }}>{error}</p>}
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <label>
          Config:{" "}
          <select value={configId} onChange={(e) => setConfigId(e.target.value)}>
            <option value="">(default)</option>
            {configs.map((c) => (
              <option key={c.id} value={c.id}>
                {c.id}
              </option>
            ))}
          </select>
        </label>
        <button onClick={run} disabled={running}>
          {running ? "Running..." : `Run selected (${selected.size || "all"})`}
        </button>
      </div>
      {challenges.map((c: any, i) => (
        <div key={i} style={{ display: "flex", gap: 8, marginBottom: 4, fontSize: 13 }}>
          <input
            type="checkbox"
            checked={selected.has(i)}
            onChange={() => toggle(i)}
            disabled={!c.id}
            title={c.id ? undefined : "This challenge has no id and can only run via 'Run all'"}
          />
          <span style={{ color: "#5f6368", minWidth: 60 }}>{c.id ?? `#${i}`}</span>
          <span>{c.input ?? c.prompt ?? JSON.stringify(c)}</span>
        </div>
      ))}
      {results.map((r, i) => (
        <div key={i} style={{ border: "1px solid #dadce0", borderRadius: 8, padding: 12, marginTop: 12 }}>
          <h4 style={{ margin: 0 }}>
            {r.challenge_id ?? `challenge ${i}`}{" "}
            <StatusPill status={r.status_code === 200 ? (wasBlocked(r) ? "blocked" : "allowed") : "error"} />
          </h4>
          <p style={{ fontSize: 13 }}>{r.challenge?.input ?? (r.challenge as any)?.prompt ?? ""}</p>
          <JsonBlock data={r.response} />
        </div>
      ))}
    </div>
  );
}
