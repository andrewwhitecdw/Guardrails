import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { JsonBlock } from "../components";
import { Button, Card, toast } from "../ui";
import { colors } from "../theme";
import type { StatusResponse } from "../types";

const HOOK_INSTRUCTIONS = `The guardrails server does not have the admin hook installed.

To enable config reload, copy dashboard/admin_hook/guardrails_admin.py into
your guardrails config folder and wire it from that folder's config.py:

  import importlib.util
  import os

  def _load_admin_hook(app):
      path = os.path.join(os.path.dirname(__file__), "guardrails_admin.py")
      spec = importlib.util.spec_from_file_location("guardrails_admin", path)
      module = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(module)
      module.init(app)

  def init(app):
      _load_admin_hook(app)

Then restart the guardrails server.`;

export default function AdminPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [configId, setConfigId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .status()
      .then((s) => {
        setStatus(s);
        setError(null);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  useEffect(load, [load]);

  const reload = async () => {
    try {
      const result: any = await api.adminReload(configId || undefined);
      toast(`Reloaded: ${JSON.stringify(result)}`, "success");
      setTimeout(load, 1000);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const configs = status?.guardrails.configs ?? [];

  return (
    <div>
      {error && <p style={{ color: colors.red, whiteSpace: "pre-wrap" }}>{error}</p>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16, marginBottom: 16 }}>
        <Card title="Server">
          <dl style={{ margin: 0, fontSize: 13 }}>
            <div style={{ marginBottom: 8 }}>
              <dt style={{ color: colors.muted, fontSize: 12 }}>Health</dt>
              <dd style={{ margin: "2px 0 0" }}>
                <strong style={{ color: status?.guardrails.healthy ? colors.green : colors.red }}>
                  {status?.guardrails.healthy ? "healthy" : "unreachable"}
                </strong>{" "}
                <span style={{ color: colors.muted }}>({status?.guardrails.url})</span>
              </dd>
            </div>
            <div>
              <dt style={{ color: colors.muted, fontSize: 12 }}>Admin hook</dt>
              <dd style={{ margin: "2px 0 0", color: status?.admin_hook ? colors.green : colors.amber }}>
                {status?.admin_hook ? "installed" : "not installed"}
              </dd>
            </div>
          </dl>
        </Card>
        <Card title="Configs">
          {configs.length === 0 ? (
            <em>No configs reported (server unreachable or none loaded).</em>
          ) : (
            <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {configs.map((c) => (
                <span
                  key={c.id}
                  style={{
                    border: `1px solid ${colors.panelBorder}`,
                    borderRadius: 999,
                    padding: "3px 12px",
                    fontSize: 12,
                    fontFamily: "monospace",
                  }}
                >
                  {c.id}
                </span>
              ))}
            </span>
          )}
        </Card>
      </div>
      <Card title="Models" style={{ marginBottom: 16 }}>
        <JsonBlock data={status?.guardrails.models ?? null} />
      </Card>
      <Card title="Reload config">
        {status && !status.admin_hook && (
          <pre
            style={{
              background: "#26200f",
              border: `1px solid ${colors.amber}`,
              color: colors.amber,
              borderRadius: 6,
              padding: 12,
              fontSize: 12,
              whiteSpace: "pre-wrap",
              marginTop: 0,
            }}
          >
            {HOOK_INSTRUCTIONS}
          </pre>
        )}
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select value={configId} onChange={(e) => setConfigId(e.target.value)} aria-label="Config">
            <option value="">all configs</option>
            {configs.map((c) => (
              <option key={c.id} value={c.id}>
                {c.id}
              </option>
            ))}
          </select>
          <Button variant="primary" onClick={reload} disabled={!status?.admin_hook}>
            Reload
          </Button>
        </div>
      </Card>
    </div>
  );
}
