import { useEffect, useRef, useState, type CSSProperties } from "react";

import { api, extractSseText } from "../api";
import { JsonBlock, RailBars } from "../components";
import { Button, Card, Spinner, toast } from "../ui";
import { colors } from "../theme";
import type { StatusResponse } from "../types";

interface ConsoleResult {
  output: string;
  log?: {
    activated_rails?: { name?: string; stop?: boolean; duration?: number; type?: string }[];
    stats?: Record<string, number>;
  };
  raw: unknown;
}

const labelStyle: CSSProperties = {
  display: "block",
  fontSize: 12,
  color: colors.muted,
  marginBottom: 4,
};

export default function ConsolePage() {
  const [configs, setConfigs] = useState<{ id: string }[]>([]);
  const [configId, setConfigId] = useState("");
  const [system, setSystem] = useState("");
  const [prompt, setPrompt] = useState("");
  const [useStream, setUseStream] = useState(false);
  const [result, setResult] = useState<ConsoleResult | null>(null);
  const [running, setRunning] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    api
      .status()
      .then((s: StatusResponse) => {
        setConfigs(s.guardrails.configs ?? []);
        if (s.guardrails.configs?.length) setConfigId(s.guardrails.configs[0].id);
      })
      .catch((e) => toast((e as Error).message, "error"));
  }, []);

  const run = async () => {
    setRunning(true);
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
      toast((e as Error).message, "error");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <p style={{ fontSize: 13, color: colors.muted, marginTop: 0 }}>
        Send a test prompt through the recording pipeline. Every run is stored
        as a request record (source=console) and appears on the Requests page.
      </p>
      <Card title="New prompt">
        <div style={{ display: "flex", gap: 16, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            Config
            <select value={configId} onChange={(e) => setConfigId(e.target.value)}>
              <option value="">(default)</option>
              {configs.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.id}
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            <input type="checkbox" checked={useStream} onChange={(e) => setUseStream(e.target.checked)} />
            stream
          </label>
        </div>
        <label style={labelStyle}>
          System prompt (optional)
          <input
            value={system}
            onChange={(e) => setSystem(e.target.value)}
            style={{ width: "100%", marginTop: 4 }}
          />
        </label>
        <label style={labelStyle}>
          User message
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={4}
            style={{ width: "100%", marginTop: 4, resize: "vertical" }}
          />
        </label>
        <Button variant="primary" onClick={run} disabled={running || !prompt.trim()}>
          {running ? (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <Spinner size={14} /> Running...
            </span>
          ) : (
            "Send"
          )}
        </Button>
      </Card>
      {result && (
        <Card title="Response" style={{ marginTop: 16 }}>
          <pre style={{ background: "#141414", border: `1px solid ${colors.panelBorder}`, borderRadius: 6, padding: 12, whiteSpace: "pre-wrap", fontSize: 13, margin: 0 }}>
            {result.output}
          </pre>
          {result.log && (
            <>
              <h4 style={{ color: colors.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 1 }}>Activated rails</h4>
              <RailBars rails={(result.log.activated_rails ?? []).map((r) => ({ ...r, stop: r.stop ?? false }))} />
              {result.log.stats && (
                <>
                  <h4 style={{ color: colors.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 1 }}>Stats</h4>
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
          <h4 style={{ color: colors.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 1 }}>Raw response</h4>
          <JsonBlock data={result.raw} />
        </Card>
      )}
    </div>
  );
}
