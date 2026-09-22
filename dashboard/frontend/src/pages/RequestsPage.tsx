import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { SourceTag, StatusPill, formatTs } from "../components";
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
      setError(null);
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
      <h1>Requests</h1>
      {error && <p style={{ color: "#b3261e" }}>{error}</p>}
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <select value={rangeMs} onChange={(e) => { setOffset(0); setSelectedId(null); setRangeMs(Number(e.target.value)); }}>
          {RANGES.map(([label, ms]) => (
            <option key={label} value={ms}>
              {label}
            </option>
          ))}
        </select>
        <select value={filters.configId} onChange={(e) => update({ configId: e.target.value })}>
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
        <select value={filters.status} onChange={(e) => update({ status: e.target.value })}>
          <option value="">any status</option>
          <option value="allowed">allowed</option>
          <option value="blocked">blocked</option>
          <option value="error">error</option>
        </select>
        <select value={filters.source} onChange={(e) => update({ source: e.target.value })}>
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
          style={{ flex: 1 }}
        />
        <button onClick={load}>Refresh</button>
      </div>
      <p style={{ fontSize: 13, color: "#5f6368" }}>{data.total} records</p>
      <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "2px solid #dadce0" }}>
            <th>Time</th><th>Source</th><th>Config</th><th>Status</th><th>Input</th><th>Output</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((r) => (
            <tr
              key={r.id}
              onClick={() => setSelectedId(r.id)}
              style={{
                borderBottom: "1px solid #eee",
                cursor: "pointer",
                background: r.id === selectedId ? "#e8f0fe" : undefined,
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
      {data.items.length === 0 && !error && <p style={{ color: "#5f6368" }}>No records match the current filters.</p>}
      <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          Previous
        </button>
        <button
          disabled={offset + PAGE_SIZE >= data.total}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          Next
        </button>
      </div>
      {selected && <RequestDetail record={selected} />}
    </div>
  );
}
