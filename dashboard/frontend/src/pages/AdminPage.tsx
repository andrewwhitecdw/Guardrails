import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { JsonBlock } from "../components";
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
  const [message, setMessage] = useState<string | null>(null);
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
    setMessage(null);
    setError(null);
    try {
      const result: any = await api.adminReload(configId || undefined);
      setMessage(`Reloaded: ${JSON.stringify(result)}`);
      setTimeout(load, 1000);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const configs = status?.guardrails.configs ?? [];

  return (
    <div>
      <h1>Admin</h1>
      {error && <p style={{ color: "#b3261e", whiteSpace: "pre-wrap" }}>{error}</p>}
      {message && <p style={{ color: "#137333" }}>{message}</p>}
      <h3>Server</h3>
      {status && (
        <ul>
          <li>
            Health:{" "}
            <strong style={{ color: status.guardrails.healthy ? "#137333" : "#b3261e" }}>
              {status.guardrails.healthy ? "healthy" : "unreachable"}
            </strong>{" "}
            ({status.guardrails.url})
          </li>
          <li>Admin hook: {status.admin_hook ? "installed" : "not installed"}</li>
        </ul>
      )}
      <h3>Configs</h3>
      {configs.length === 0 && <em>No configs reported (server unreachable or none loaded).</em>}
      <ul>
        {configs.map((c) => (
          <li key={c.id}>{c.id}</li>
        ))}
      </ul>
      <h3>Models</h3>
      <JsonBlock data={status?.guardrails.models ?? null} />
      <h3>Reload config</h3>
      {status && !status.admin_hook && (
        <pre style={{ background: "#fef7e0", border: "1px solid #f9ab00", borderRadius: 6, padding: 12, fontSize: 12, whiteSpace: "pre-wrap" }}>
          {HOOK_INSTRUCTIONS}
        </pre>
      )}
      <div style={{ display: "flex", gap: 8 }}>
        <select value={configId} onChange={(e) => setConfigId(e.target.value)}>
          <option value="">all configs</option>
          {configs.map((c) => (
            <option key={c.id} value={c.id}>
              {c.id}
            </option>
          ))}
        </select>
        <button onClick={reload} disabled={!status?.admin_hook}>
          Reload
        </button>
      </div>
    </div>
  );
}
