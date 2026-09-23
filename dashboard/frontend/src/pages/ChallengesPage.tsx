import { useEffect, useState } from "react";

import { api } from "../api";
import { JsonBlock, StatusPill } from "../components";
import { Button, Card, toast } from "../ui";
import { colors } from "../theme";
import type { ChallengeRunResult } from "../types";

export default function ChallengesPage() {
  const [configs, setConfigs] = useState<{ id: string }[]>([]);
  const [configId, setConfigId] = useState("");
  const [challenges, setChallenges] = useState<Record<string, unknown>[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [results, setResults] = useState<ChallengeRunResult[]>([]);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    Promise.all([api.status(), api.challenges()])
      .then(([s, c]) => {
        setConfigs(s.guardrails.configs ?? []);
        if (s.guardrails.configs?.length) setConfigId(s.guardrails.configs[0].id);
        setChallenges(c.items);
      })
      .catch((e) => toast((e as Error).message, "error"));
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
    try {
      const ids = [...selected].map((i) => challenges[i]).map((c: any) => c.id).filter(Boolean);
      const data = await api.runChallenges({ config_id: configId || undefined, challenge_ids: ids });
      setResults(data.results);
      toast(`Ran ${data.results.length} challenge(s)`, "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setRunning(false);
    }
  };

  const wasBlocked = (r: ChallengeRunResult) =>
    Boolean(r.response?.guardrails?.log?.activated_rails?.some((rail: any) => rail.stop));

  return (
    <div>
      <p style={{ fontSize: 13, color: colors.muted, marginTop: 0 }}>
        Red-teaming challenge prompts served by the guardrails server
        (/v1/challenges). Runs are recorded with source=challenge.
      </p>
      <Card
        title="Challenges"
        actions={
          <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <select value={configId} onChange={(e) => setConfigId(e.target.value)} aria-label="Config">
              <option value="">(default)</option>
              {configs.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.id}
                </option>
              ))}
            </select>
            <Button variant="primary" onClick={run} disabled={running}>
              {running ? "Running..." : `Run selected (${selected.size || "all"})`}
            </Button>
          </span>
        }
        style={{ marginBottom: 16 }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {challenges.map((c: any, i) => (
            <label
              key={i}
              style={{ display: "flex", gap: 10, alignItems: "baseline", fontSize: 13, cursor: "pointer" }}
            >
              <input
                type="checkbox"
                checked={selected.has(i)}
                onChange={() => toggle(i)}
                disabled={!c.id}
                title={c.id ? undefined : "This challenge has no id and can only run via 'Run all'"}
              />
              <span style={{ color: colors.muted, minWidth: 60, fontFamily: "monospace" }}>{c.id ?? `#${i}`}</span>
              <span>{c.input ?? c.prompt ?? JSON.stringify(c)}</span>
            </label>
          ))}
        </div>
      </Card>
      {results.map((r, i) => (
        <Card
          key={i}
          title={r.challenge_id ?? `challenge ${i}`}
          actions={
            <StatusPill status={r.status_code === 200 ? (wasBlocked(r) ? "blocked" : "allowed") : "error"} />
          }
          style={{ marginBottom: 12 }}
        >
          <p style={{ fontSize: 13, marginTop: 0 }}>{r.challenge?.input ?? (r.challenge as any)?.prompt ?? ""}</p>
          <JsonBlock data={r.response} />
        </Card>
      ))}
    </div>
  );
}
