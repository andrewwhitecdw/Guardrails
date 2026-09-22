import { useEffect, useRef, useState } from "react";

import { api, extractSseText } from "../api";
import { RailBars } from "../components";
import type { StatusResponse } from "../types";

interface ConsoleResult {
  output: string;
  log?: {
    activated_rails?: { name?: string; stop?: boolean; duration?: number; type?: string }[];
    stats?: Record<string, number>;
  };
  raw: unknown;
}

export default function ConsolePage() {
  const [configs, setConfigs] = useState<{ id: string }[]>([]);
  const [configId, setConfigId] = useState("");
  const [system, setSystem] = useState("");
  const [prompt, setPrompt] = useState("");
  const [useStream, setUseStream] = useState(false);
  const [result, setResult] = useState<ConsoleResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    api
      .status()
      .then((s: StatusResponse) => {
        setConfigs(s.guardrails.configs ?? []);
        if (s.guardrails.configs?.length) setConfigId(s.guardrails.configs[0].id);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  const run = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    const messages = [
      ...(system.trim() ? [{ role: "system", content: system }] : []),
      { role: "user", content: prompt },
    ];
    const body = { config_id: configId || undefined, messages };
    try {
      if (useStream) {
        abortRef.current = new AbortController();
        const resp = await fetch("/api/commands/console/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...body, stream: true }),
          signal: abortRef.current.signal,
        });
        if (!resp.ok || !resp.body) throw new Error(await resp.text());
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          setResult({
            output: extractSseText(buffer),
            log: undefined,
            raw: { streamed: true },
          });
        }
      } else {
        const data: any = await api.consoleRun(body);
        const log = data?.guardrails?.log;
        setResult({
          output: data?.choices?.[0]?.message?.content ?? JSON.stringify(data),
          log,
          raw: data,
        });
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <h1>Console</h1>
      <p style={{ fontSize: 13, color: "#9d9d9d" }}>
        Send a test prompt through the recording pipeline. Every run is stored
        as a request record (source=console) and appears on the Requests page.
      </p>
      {error && <p style={{ color: "#ff5c5c" }}>{error}</p>}
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
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
        <label>
          <input type="checkbox" checked={useStream} onChange={(e) => setUseStream(e.target.checked)} />{" "}
          stream
        </label>
      </div>
      <input
        placeholder="System prompt (optional)"
        value={system}
        onChange={(e) => setSystem(e.target.value)}
        style={{ width: "100%", marginBottom: 8 }}
      />
      <textarea
        placeholder="User message..."
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={4}
        style={{ width: "100%", marginBottom: 8 }}
      />
      <button onClick={run} disabled={running || !prompt.trim()}>
        {running ? "Running..." : "Send"}
      </button>
      {result && (
        <div style={{ marginTop: 16 }}>
          <h3>Response</h3>
          <pre style={{ background: "#141414", padding: 12, borderRadius: 6, whiteSpace: "pre-wrap" }}>
            {result.output}
          </pre>
          {result.log && (
            <>
              <h4>Activated rails</h4>
              <RailBars rails={(result.log.activated_rails ?? []).map((r) => ({ ...r, stop: r.stop ?? false }))} />
              {result.log.stats && (
                <>
                  <h4>Stats</h4>
                  <ul>
                    {Object.entries(result.log.stats).map(([k, v]) => (
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
            </>
          )}
        </div>
      )}
    </div>
  );
}
