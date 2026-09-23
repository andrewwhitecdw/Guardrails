import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { SourceTag, StatusPill, formatTs } from "../components";
import { Button, Card, EmptyState } from "../ui";
import { colors } from "../theme";
import type { RecordsResponse } from "../types";
import RequestDetail from "./RequestDetail";

const PAGE_SIZE = 50;
const RANGES: [string, number][] = [
  ["all time", 0],
  ["15 minutes", 15 * 60 * 1000],
  ["1 hour", 60 * 60 * 1000],
  ["24 hours", 24 * 60 * 60 * 1000],
];

export default function RequestsPage() {
  const [filters, setFilters] = useState({ status: "", source: "", search: "", configId: "", rail: "" });
  const [rangeMs, setRangeMs] = useState(RANGES[1][1]);
  const [configs, setConfigs] = useState<{ id: string }[]>([]);
  const [data, setData] = useState<RecordsResponse>({ items: [], total: 0 });
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<RecordsResponse["items"][0] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .status()
      .then((s) => setConfigs(s.guardrails.configs ?? []))
      .catch(() => setConfigs([]));
  }, []);

  const load = useCallback(async () => {
    try {
      const end = Date.now();
      const result = await api.records({
        status: filters.status || undefined,
        source: filters.source || undefined,
        search: filters.search || undefined,
        config_id: filters.configId || undefined,
        rail: filters.rail || undefined,
        start: rangeMs > 0 ? end - rangeMs : undefined,
        end: rangeMs > 0 ? end : undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setData(result);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [filters, rangeMs, offset]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!selectedId) {
      setSelected(null);
      return;
    }
    let stale = false;
    api
      .record(selectedId)
      .then((rec) => {
        if (!stale) {
          setSelected(rec);
          setError(null);
        }
      })
      .catch((e) => {
        if (!stale) setError((e as Error).message);
      });
    return () => {
      stale = true;
    };
  }, [selectedId]);

  const update = (patch: Partial<typeof filters>) => {
    setOffset(0);
    setSelectedId(null);
    setFilters((f) => ({ ...f, ...patch }));
  };

  return (
    <div>
      {error && <p style={{ color: colors.red }}>{error}</p>}
      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <select
            value={rangeMs}
            onChange={(e) => { setOffset(0); setSelectedId(null); setRangeMs(Number(e.target.value)); }}
            aria-label="Time range"
          >
            {RANGES.map(([label, ms]) => (
              <option key={label} value={ms}>
                {label}
              </option>
            ))}
          </select>
          <select
            value={filters.configId}
            onChange={(e) => update({ configId: e.target.value })}
            aria-label="Config"
          >
            <option value="">any config</option>
            {configs.map((c) => (
              <option key={c.id} value={c.id}>
                {c.id}
              </option>
            ))}
          </select>
          <input
            placeholder="rail name..."
            value={filters.rail}
            onChange={(e) => update({ rail: e.target.value })}
            style={{ width: 140 }}
          />
          <select
            value={filters.status}
            onChange={(e) => update({ status: e.target.value })}
            aria-label="Status"
          >
            <option value="">any status</option>
            <option value="allowed">allowed</option>
            <option value="blocked">blocked</option>
            <option value="error">error</option>
          </select>
          <select
            value={filters.source}
            onChange={(e) => update({ source: e.target.value })}
            aria-label="Source"
          >
            <option value="">any source</option>
            <option value="proxy">proxy</option>
            <option value="trace_file">trace_file</option>
            <option value="console">console</option>
            <option value="check">check</option>
            <option value="challenge">challenge</option>
          </select>
          <input
            placeholder="search input/output..."
            value={filters.search}
            onChange={(e) => update({ search: e.target.value })}
            style={{ flex: 1, minWidth: 160 }}
          />
          <Button onClick={load}>Refresh</Button>
        </div>
      </Card>
      <Card
        title={`${data.total} records`}
        actions={
          <span style={{ display: "flex", gap: 8 }}>
            <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              Previous
            </Button>
            <Button
              disabled={offset + PAGE_SIZE >= data.total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </Button>
          </span>
        }
      >
        {data.items.length === 0 && !error ? (
          <EmptyState
            title="No records match the current filters"
            hint="Send a request from the Console page or widen the time range."
          />
        ) : (
          <table className="nv-table">
            <thead>
              <tr>
                <th>Time</th><th>Source</th><th>Config</th><th>Status</th><th>Input</th><th>Output</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => setSelectedId(r.id)}
                  style={{
                    cursor: "pointer",
                    background: r.id === selectedId ? "rgba(118, 185, 0, 0.15)" : undefined,
                  }}
                >
                  <td style={{ whiteSpace: "nowrap" }}>{formatTs(r.ts)}</td>
                  <td><SourceTag source={r.source} /></td>
                  <td>{r.config_id ?? ""}</td>
                  <td><StatusPill status={r.status} /></td>
                  <td style={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {r.input_summary}
                  </td>
                  <td style={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {r.output_summary}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {selected && <RequestDetail record={selected} />}
    </div>
  );
}
