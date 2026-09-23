# Dashboard UX Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the guardrails admin dashboard look and feel like a modern web application (dark pro dashboard) while keeping NVIDIA branding and changing no backend behavior.

**Architecture:** Add a small design-token module and shared UI components (`ui.tsx`) used by every page. Rewrite the app shell (grouped sidebar + sticky top bar with health pill + page actions slot) and restyle all seven pages using cards, buttons, skeletons, empty states, and a toast system. All work is in `dashboard/frontend/src` plus the `<style>` block in `dashboard/frontend/index.html`.

**Tech Stack:** React 18, TypeScript, Vite, vitest + Testing Library, recharts, react-router-dom (HashRouter). Commands run from `dashboard/frontend` unless noted. Git commands run from the repo root `/home/andrewh/code/personal/Guardrails`.

**Spec:** `docs/superpowers/specs/2026-09-22-dashboard-ux-modernization-design.md`

**Reference:** The dashboard server is already running on http://localhost:8500 serving `dashboard/frontend/dist`, so after each `npm run build` the result is live immediately.

---

### Task 1: Design tokens and global CSS

**Files:**
- Create: `dashboard/frontend/src/theme.ts`
- Modify: `dashboard/frontend/index.html` (the existing `<style>` block)

- [ ] **Step 1: Create `src/theme.ts`**

```ts
import type { CSSProperties } from "react";

export const colors = {
  bg: "#0f0f0f",
  panel: "#161616",
  panelBorder: "#2a2a2a",
  text: "#e8e8e8",
  muted: "#9d9d9d",
  green: "#76b900",
  red: "#ff5c5c",
  amber: "#f79009",
} as const;

export const cardStyle: CSSProperties = {
  background: colors.panel,
  border: `1px solid ${colors.panelBorder}`,
  borderRadius: 8,
};
```

- [ ] **Step 2: Replace the `<style>` block in `index.html`**

Replace the current `<style>...</style>` with:

```html
    <style>
      html, body { margin: 0; background: #0f0f0f; }
      *, *::before, *::after { box-sizing: border-box; }
      input, select, textarea, button { background: #1a1a1a; color: #e8e8e8; border: 1px solid #333333; border-radius: 4px; padding: 6px 8px; font: inherit; }
      input:focus-visible, select:focus-visible, textarea:focus-visible, button:focus-visible { outline: 2px solid rgba(118, 185, 0, 0.5); outline-offset: 1px; }
      .nv-table { width: 100%; border-collapse: collapse; font-size: 13px; }
      .nv-table thead th { text-align: left; padding: 8px 10px; border-bottom: 2px solid #2a2a2a; color: #9d9d9d; font-weight: 600; white-space: nowrap; }
      .nv-table tbody td { padding: 8px 10px; border-bottom: 1px solid #1f1f1f; vertical-align: top; }
      .nv-table tbody tr:hover { background: #1a1a1a; }
      @keyframes nv-pulse { 0%, 100% { opacity: 0.45; } 50% { opacity: 0.9; } }
      @keyframes nv-spin { to { transform: rotate(360deg); } }
    </style>
```

- [ ] **Step 3: Verify the build still passes**

Run: `cd dashboard/frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add dashboard/frontend/src/theme.ts dashboard/frontend/index.html
git commit -m "feat(dashboard): add design tokens and global styles"
```

---

### Task 2: Shared UI components (TDD)

**Files:**
- Create: `dashboard/frontend/src/ui.test.tsx`
- Create: `dashboard/frontend/src/ui.tsx`

- [ ] **Step 1: Write the failing tests**

`src/ui.test.tsx`:

```tsx
import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button, EmptyState, Skeleton, Spinner, Toaster, toast } from "./ui";

describe("Button", () => {
  it("renders primary variant with green background", () => {
    render(<Button variant="primary">Go</Button>);
    const btn = screen.getByRole("button", { name: "Go" });
    expect(btn.style.backgroundColor).toBe("rgb(118, 185, 0)");
  });

  it("renders danger variant with red text", () => {
    render(<Button variant="danger">Delete</Button>);
    expect(screen.getByRole("button", { name: "Delete" }).style.color).toBe("rgb(255, 92, 92)");
  });

  it("is disabled when asked", () => {
    render(<Button disabled>Nope</Button>);
    expect(screen.getByRole("button", { name: "Nope" })).toHaveProperty("disabled", true);
  });
});

describe("EmptyState", () => {
  it("renders title and hint", () => {
    render(<EmptyState title="Nothing here" hint="Try again" />);
    expect(screen.getByText("Nothing here")).toBeTruthy();
    expect(screen.getByText("Try again")).toBeTruthy();
  });
});

describe("Skeleton", () => {
  it("renders a pulsing placeholder", () => {
    const { container } = render(<Skeleton width={100} height={10} />);
    expect((container.firstChild as HTMLElement).style.animation).toContain("nv-pulse");
  });
});

describe("Spinner", () => {
  it("renders a status indicator", () => {
    render(<Spinner />);
    expect(screen.getByRole("status")).toBeTruthy();
  });
});

describe("toast", () => {
  it("shows a toast in the toaster", () => {
    render(<Toaster />);
    act(() => toast("Saved", "success"));
    expect(screen.getByText("Saved")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard/frontend && npx vitest run src/ui.test.tsx`
Expected: FAIL — cannot find module `./ui`.

- [ ] **Step 3: Implement `src/ui.tsx`**

```tsx
import {
  useEffect,
  useState,
  type ButtonHTMLAttributes,
  type CSSProperties,
  type ReactNode,
} from "react";

import { cardStyle, colors } from "./theme";

export function Card({
  title,
  actions,
  children,
  style,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <section style={{ ...cardStyle, padding: 16, ...style }}>
      {(title || actions) && (
        <header
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 8,
            marginBottom: 12,
          }}
        >
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{title}</h3>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

type ButtonVariant = "primary" | "secondary" | "danger";

export function Button({
  variant = "secondary",
  style,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  const variantStyle: Record<ButtonVariant, CSSProperties> = {
    primary: {
      backgroundColor: colors.green,
      color: "#000000",
      border: `1px solid ${colors.green}`,
      fontWeight: 600,
    },
    secondary: {
      backgroundColor: "#1a1a1a",
      color: colors.text,
      border: `1px solid ${colors.panelBorder}`,
    },
    danger: {
      backgroundColor: "transparent",
      color: colors.red,
      border: `1px solid ${colors.red}`,
    },
  };
  return (
    <button
      {...rest}
      style={{
        padding: "6px 14px",
        borderRadius: 4,
        cursor: rest.disabled ? "not-allowed" : "pointer",
        opacity: rest.disabled ? 0.5 : 1,
        ...variantStyle[variant],
        ...style,
      }}
    />
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div style={{ textAlign: "center", padding: "32px 16px", color: colors.muted }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: colors.text, marginBottom: 4 }}>
        {title}
      </div>
      {hint && <div style={{ fontSize: 13 }}>{hint}</div>}
    </div>
  );
}

export function Skeleton({
  width = "100%",
  height = 14,
  style,
}: {
  width?: number | string;
  height?: number;
  style?: CSSProperties;
}) {
  return (
    <div
      aria-hidden="true"
      style={{
        width,
        height,
        borderRadius: 4,
        background: "#1f1f1f",
        animation: "nv-pulse 1.5s ease-in-out infinite",
        ...style,
      }}
    />
  );
}

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <span
      role="status"
      aria-label="loading"
      style={{
        display: "inline-block",
        width: size,
        height: size,
        borderRadius: "50%",
        border: "2px solid #2a2a2a",
        borderTopColor: colors.green,
        animation: "nv-spin 0.8s linear infinite",
      }}
    />
  );
}

type ToastKind = "success" | "error" | "info";

interface ToastItem {
  id: number;
  message: string;
  kind: ToastKind;
}

let toasts: ToastItem[] = [];
let nextToastId = 1;
const toastListeners = new Set<(items: ToastItem[]) => void>();

function emitToasts() {
  for (const listener of toastListeners) listener(toasts);
}

export function toast(message: string, kind: ToastKind = "info") {
  const item = { id: nextToastId++, message, kind };
  toasts = [...toasts, item];
  emitToasts();
  setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== item.id);
    emitToasts();
  }, 4000);
}

const toastColors: Record<ToastKind, string> = {
  success: colors.green,
  error: colors.red,
  info: colors.muted,
};

export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>(toasts);
  useEffect(() => {
    const listener = (next: ToastItem[]) => setItems(next);
    toastListeners.add(listener);
    return () => {
      toastListeners.delete(listener);
    };
  }, []);
  if (!items.length) return null;
  return (
    <div style={{ position: "fixed", right: 16, bottom: 16, display: "flex", flexDirection: "column", gap: 8, zIndex: 100 }}>
      {items.map((t) => (
        <div
          key={t.id}
          role="alert"
          style={{
            background: colors.panel,
            border: `1px solid ${colors.panelBorder}`,
            borderLeft: `3px solid ${toastColors[t.kind]}`,
            borderRadius: 6,
            padding: "10px 14px",
            fontSize: 13,
            maxWidth: 360,
            boxShadow: "0 4px 16px rgba(0, 0, 0, 0.5)",
          }}
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard/frontend && npx vitest run src/ui.test.tsx`
Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add dashboard/frontend/src/ui.tsx dashboard/frontend/src/ui.test.tsx
git commit -m "feat(dashboard): add shared UI components and toast system"
```

---

### Task 3: Restyle existing components to use tokens

**Files:**
- Modify: `dashboard/frontend/src/components.tsx` (full rewrite)

The existing tests for these components must keep passing unchanged (`components.test.tsx`).

- [ ] **Step 1: Rewrite `src/components.tsx`**

```tsx
import { cardStyle, colors } from "./theme";
import type { RailInfo } from "./types";

export function StatusPill({ status }: { status: string }) {
  const background =
    status === "blocked" ? colors.red : status === "error" ? colors.amber : colors.green;
  return (
    <span
      style={{
        background,
        color: "#000000",
        borderRadius: 10,
        padding: "2px 10px",
        fontSize: 11,
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: 0.5,
      }}
    >
      {status}
    </span>
  );
}

export function SourceTag({ source }: { source: string }) {
  return (
    <span
      style={{
        color: colors.muted,
        fontSize: 11,
        border: `1px solid ${colors.panelBorder}`,
        borderRadius: 10,
        padding: "1px 8px",
        textTransform: "uppercase",
        letterSpacing: 0.5,
      }}
    >
      {source}
    </span>
  );
}

export function JsonBlock({ data }: { data: unknown }) {
  if (data === null || data === undefined) return <em>none</em>;
  return (
    <pre
      style={{
        ...cardStyle,
        background: "#141414",
        padding: 12,
        overflow: "auto",
        maxHeight: 320,
        fontSize: 12,
        margin: 0,
      }}
    >
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

export function RailBars({ rails }: { rails: RailInfo[] }) {
  if (!rails.length) return <em>No rails activated.</em>;
  const max = Math.max(0.001, ...rails.map((r) => r.duration ?? 0));
  return (
    <div>
      {rails.map((rail, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <span style={{ minWidth: 240, fontSize: 13 }}>
            {rail.name}
            {rail.stop ? " (stopped)" : ""}
            {rail.type ? ` [${rail.type}]` : ""}
          </span>
          <div
            style={{
              height: 12,
              background: rail.stop ? colors.red : colors.green,
              borderRadius: 3,
              width: `${Math.max(2, ((rail.duration ?? 0) / max) * 100)}%`,
            }}
          />
          <span style={{ fontSize: 12, color: colors.muted }}>
            {rail.duration != null ? `${Math.round(rail.duration * 1000)} ms` : "n/a"}
          </span>
        </div>
      ))}
    </div>
  );
}

export function formatTs(ts: number): string {
  return new Date(ts).toLocaleString();
}

export function formatMs(ms: number | null | undefined): string {
  return ms == null ? "n/a" : `${Math.round(ms)} ms`;
}
```

- [ ] **Step 2: Run the component tests**

Run: `cd dashboard/frontend && npx vitest run src/components.test.tsx`
Expected: 4 tests pass (text content unchanged).

- [ ] **Step 3: Commit**

```bash
git add dashboard/frontend/src/components.tsx
git commit -m "feat(dashboard): restyle status pills, tags, and JSON blocks"
```

---

### Task 4: App shell — grouped nav, top bar, health pill, page actions

**Files:**
- Modify: `dashboard/frontend/src/App.tsx` (full rewrite)

- [ ] **Step 1: Rewrite `src/App.tsx`**

```tsx
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { HashRouter, NavLink, Route, Routes, useLocation } from "react-router-dom";

import { api } from "./api";
import AdminPage from "./pages/AdminPage";
import ChallengesPage from "./pages/ChallengesPage";
import ConsolePage from "./pages/ConsolePage";
import MetricsPage from "./pages/MetricsPage";
import OverviewPage from "./pages/OverviewPage";
import RequestsPage from "./pages/RequestsPage";
import TelemetryPage from "./pages/TelemetryPage";
import { Toaster } from "./ui";
import { colors } from "./theme";

const NAV: { label: string; items: [string, string, string][] }[] = [
  {
    label: "Monitor",
    items: [
      ["/", "Overview", "M3 3h7v7H3z M14 3h7v7h-7z M14 14h7v7h-7z M3 14h7v7H3z"],
      ["/requests", "Requests", "M8 6h13 M8 12h13 M8 18h13 M3 6h.01 M3 12h.01 M3 18h.01"],
      ["/metrics", "Metrics", "M3 12h4l3 8 4-16 3 8h4"],
      ["/telemetry", "Telemetry", "M5 12.9a10 10 0 0 1 14 0 M8.5 16.4a5 5 0 0 1 7 0 M12 20h.01"],
    ],
  },
  {
    label: "Tools",
    items: [
      ["/console", "Console", "M4 17l6-5-6-5 M12 19h8"],
      ["/challenges", "Challenges", "M12 22s8-3 8-10V5l-8-3-8 3v7c0 7 8 10 8 10z"],
    ],
  },
  {
    label: "System",
    items: [["/admin", "Admin", "M4 21v-7 M4 10V3 M12 21v-9 M12 8V3 M20 21v-5 M20 12V3 M1 14h6 M9 8h6 M17 16h6"]],
  },
];

const PageActionsContext = createContext<(node: ReactNode | null) => void>(() => {});

/** Pages call this to render controls into the sticky top bar. */
export function usePageActions() {
  return useContext(PageActionsContext);
}

function NavIcon({ d }: { d: string }) {
  return (
    <svg
      width={15}
      height={15}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flexShrink: 0 }}
    >
      <path d={d} />
    </svg>
  );
}

function NvidiaMark() {
  return (
    <svg viewBox="0 0 100 100" width={28} height={28} aria-hidden="true">
      <g fill="none" stroke={colors.green} strokeWidth={8} strokeLinecap="round">
        <path d="M18 50 A32 32 0 0 1 82 50" />
        <path d="M31 50 A19 19 0 0 1 69 50" />
        <path d="M44 50 A6 6 0 0 1 56 50" />
        <path d="M18 63 A32 32 0 0 0 82 63" opacity={0.55} />
        <path d="M31 63 A19 19 0 0 0 69 63" opacity={0.55} />
      </g>
    </svg>
  );
}

function pageTitle(pathname: string): string {
  for (const group of NAV) {
    for (const [to, label] of group.items) {
      if (to === "/" ? pathname === "/" : pathname.startsWith(to)) return label;
    }
  }
  return "Dashboard";
}

function TopBar({ health, actions }: { health: { healthy: boolean; url: string } | null; actions: ReactNode }) {
  const location = useLocation();
  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 10,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
        padding: "12px 24px",
        background: "rgba(15, 15, 15, 0.92)",
        backdropFilter: "blur(6px)",
        borderBottom: `1px solid ${colors.panelBorder}`,
      }}
    >
      <h1 style={{ margin: 0, fontSize: 18, fontWeight: 650 }}>{pageTitle(location.pathname)}</h1>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        {actions}
        {health && (
          <span
            title={health.url}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 12,
              color: colors.muted,
              border: `1px solid ${colors.panelBorder}`,
              borderRadius: 999,
              padding: "3px 10px",
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: health.healthy ? colors.green : colors.red,
              }}
            />
            {health.healthy ? "healthy" : "unreachable"}
          </span>
        )}
      </div>
    </header>
  );
}

function Shell() {
  const [actions, setActions] = useState<ReactNode>(null);
  const [health, setHealth] = useState<{ healthy: boolean; url: string } | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => {
      api
        .status()
        .then((s) => {
          if (alive) setHealth({ healthy: s.guardrails.healthy, url: s.guardrails.url });
        })
        .catch(() => {
          if (alive) setHealth((h) => ({ healthy: false, url: h?.url ?? "" }));
        });
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <div
      style={{
        display: "flex",
        minHeight: "100vh",
        fontFamily: "'Segoe UI', system-ui, sans-serif",
        color: colors.text,
        background: colors.bg,
        fontSize: 14,
      }}
    >
      <nav
        style={{
          width: 218,
          background: "#000000",
          borderRight: `1px solid ${colors.panelBorder}`,
          padding: "16px 12px",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 6px" }}>
          <NvidiaMark />
          <span style={{ fontSize: 19, fontWeight: 700, letterSpacing: 2, color: "#ffffff" }}>
            NVIDIA
          </span>
        </div>
        <div
          style={{
            fontSize: 10,
            color: colors.green,
            textTransform: "uppercase",
            letterSpacing: 1.5,
            margin: "4px 0 20px 44px",
          }}
        >
          Guardrails
        </div>
        {NAV.map((group) => (
          <div key={group.label} style={{ marginBottom: 18 }}>
            <div
              style={{
                fontSize: 10,
                textTransform: "uppercase",
                letterSpacing: 1.5,
                color: "#5f5f5f",
                padding: "0 10px 6px",
              }}
            >
              {group.label}
            </div>
            {group.items.map(([to, label, icon]) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                style={({ isActive }) => ({
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  textDecoration: "none",
                  color: isActive ? "#000000" : colors.muted,
                  background: isActive ? colors.green : "transparent",
                  fontWeight: isActive ? 600 : 400,
                  borderRadius: 6,
                  padding: "7px 10px",
                  fontSize: 13,
                  marginBottom: 2,
                })}
              >
                <NavIcon d={icon} />
                {label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <TopBar health={health} actions={actions} />
        <main style={{ flex: 1, padding: 24, overflow: "auto" }}>
          <PageActionsContext.Provider value={setActions}>
            <Routes>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/requests" element={<RequestsPage />} />
              <Route path="/metrics" element={<MetricsPage />} />
              <Route path="/telemetry" element={<TelemetryPage />} />
              <Route path="/console" element={<ConsolePage />} />
              <Route path="/challenges" element={<ChallengesPage />} />
              <Route path="/admin" element={<AdminPage />} />
            </Routes>
          </PageActionsContext.Provider>
        </main>
      </div>
      <Toaster />
    </div>
  );
}

export default function App() {
  return (
    <HashRouter>
      <Shell />
    </HashRouter>
  );
}
```

- [ ] **Step 2: Verify the build**

Run: `cd dashboard/frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Run all frontend tests**

Run: `cd dashboard/frontend && npx vitest run`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add dashboard/frontend/src/App.tsx
git commit -m "feat(dashboard): grouped nav, sticky top bar with health pill, page actions slot"
```

---

### Task 5: Overview page

**Files:**
- Modify: `dashboard/frontend/src/pages/OverviewPage.tsx` (full rewrite)

Data fetching logic is unchanged (status + stats polled every 5s). The range selector moves to the top bar via `usePageActions`; stat cards, chart, and ingestion block are modernized; skeletons while the first load is in flight.

- [ ] **Step 1: Rewrite `src/pages/OverviewPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { usePageActions } from "../App";
import { api } from "../api";
import { formatMs } from "../components";
import { Card, Skeleton } from "../ui";
import { cardStyle, colors } from "../theme";
import type { OverviewStats, StatusResponse } from "../types";

const RANGES: [string, number][] = [
  ["15 minutes", 15 * 60 * 1000],
  ["1 hour", 60 * 60 * 1000],
  ["24 hours", 24 * 60 * 60 * 1000],
];

const tooltipStyle = {
  backgroundColor: colors.panel,
  border: `1px solid ${colors.panelBorder}`,
  borderRadius: 8,
  fontSize: 12,
} as const;

export default function OverviewPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [rangeMs, setRangeMs] = useState(RANGES[0][1]);
  const [error, setError] = useState<string | null>(null);
  const setActions = usePageActions();

  useEffect(() => {
    setActions(
      <select
        value={rangeMs}
        onChange={(e) => setRangeMs(Number(e.target.value))}
        aria-label="Time range"
      >
        {RANGES.map(([label, ms]) => (
          <option key={label} value={ms}>
            {label}
          </option>
        ))}
      </select>,
    );
    return () => setActions(null);
  }, [rangeMs, setActions]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const end = Date.now();
        const [s, o] = await Promise.all([
          api.status(),
          api.overview(end - rangeMs, end),
        ]);
        if (alive) {
          setStatus(s);
          setStats(o);
          setError(null);
        }
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [rangeMs]);

  const healthy = status?.guardrails.healthy;
  const chartData = (stats?.buckets ?? []).map((b) => ({
    time: new Date(b.ts).toLocaleTimeString(),
    requests: b.count,
    blocked: b.blocked,
  }));

  return (
    <div>
      {error && <p style={{ color: colors.red }}>{error}</p>}
      {status && (
        <p style={{ marginTop: 0, color: colors.muted, fontSize: 13 }}>
          Guardrails server{" "}
          <strong style={{ color: healthy ? colors.green : colors.red }}>
            {healthy ? "healthy" : "unreachable"}
          </strong>{" "}
          ({status.guardrails.url}) — admin hook{" "}
          {status.admin_hook ? (
            <span style={{ color: colors.green }}>installed</span>
          ) : (
            <span style={{ color: colors.amber }}>not installed</span>
          )}
        </p>
      )}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
        {stats ? (
          <>
            <StatCard label="Requests" value={stats.count} />
            <StatCard label="Blocked" value={stats.blocked} />
            <StatCard label="Errors" value={stats.errors} />
            <StatCard label="p50 latency" value={formatMs(stats.p50_ms)} />
            <StatCard label="p95 latency" value={formatMs(stats.p95_ms)} />
            <StatCard label="Input tokens" value={stats.input_tokens} />
            <StatCard label="Output tokens" value={stats.output_tokens} />
          </>
        ) : (
          Array.from({ length: 7 }, (_, i) => (
            <Skeleton key={i} width={130} height={64} />
          ))
        )}
      </div>
      <Card title="Requests over selected range">
        <div style={{ width: "100%", height: 260 }}>
          <ResponsiveContainer>
            <AreaChart data={chartData}>
              <CartesianGrid stroke="#1f1f1f" strokeDasharray="3 3" />
              <XAxis dataKey="time" stroke={colors.muted} tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} stroke={colors.muted} tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: colors.muted }} />
              <Area
                type="monotone"
                dataKey="requests"
                name="requests"
                stroke={colors.green}
                fill={colors.green}
                fillOpacity={0.2}
              />
              <Area
                type="monotone"
                dataKey="blocked"
                name="blocked"
                stroke={colors.red}
                fill={colors.red}
                fillOpacity={0.3}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>
      {status && (
        <Card title="Ingestion" style={{ marginTop: 20 }}>
          <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, fontSize: 13 }}>
            <div>
              <dt style={{ color: colors.muted, fontSize: 12 }}>Trace globs</dt>
              <dd style={{ margin: "2px 0 0" }}>{status.ingestion.trace_globs.join(", ") || "none"}</dd>
            </div>
            <div>
              <dt style={{ color: colors.muted, fontSize: 12 }}>Prometheus URL</dt>
              <dd style={{ margin: "2px 0 0" }}>{status.ingestion.prom_url || "none"}</dd>
            </div>
            <div>
              <dt style={{ color: colors.muted, fontSize: 12 }}>Records written</dt>
              <dd style={{ margin: "2px 0 0" }}>
                {status.ingestion.records_written} (duplicates skipped:{" "}
                {status.ingestion.records_dropped_duplicates})
              </dd>
            </div>
            <div>
              <dt style={{ color: colors.muted, fontSize: 12 }}>Malformed lines</dt>
              <dd style={{ margin: "2px 0 0" }}>
                {Object.entries(status.ingestion.malformed).length
                  ? Object.entries(status.ingestion.malformed)
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(", ")
                  : "none"}
              </dd>
            </div>
          </dl>
        </Card>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value?: number | string | null }) {
  return (
    <div style={{ ...cardStyle, borderLeft: `3px solid ${colors.green}`, padding: "12px 16px", minWidth: 120, flex: "1 1 120px" }}>
      <div style={{ fontSize: 12, color: colors.muted }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 650 }}>{value ?? "n/a"}</div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build and tests**

Run: `cd dashboard/frontend && npm run build && npx vitest run`
Expected: build succeeds, all tests pass.

- [ ] **Step 3: Commit**

```bash
git add dashboard/frontend/src/pages/OverviewPage.tsx
git commit -m "feat(dashboard): modernize overview page with cards, skeletons, top-bar range picker"
```

---

### Task 6: Requests page and request detail

**Files:**
- Modify: `dashboard/frontend/src/pages/RequestsPage.tsx` (full rewrite)
- Modify: `dashboard/frontend/src/pages/RequestDetail.tsx` (full rewrite)

- [ ] **Step 1: Rewrite `src/pages/RequestsPage.tsx`**

```tsx
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
```

- [ ] **Step 2: Rewrite `src/pages/RequestDetail.tsx`**

```tsx
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
```

- [ ] **Step 3: Verify build and tests**

Run: `cd dashboard/frontend && npm run build && npx vitest run`
Expected: build succeeds, all tests pass.

- [ ] **Step 4: Commit**

```bash
git add dashboard/frontend/src/pages/RequestsPage.tsx dashboard/frontend/src/pages/RequestDetail.tsx
git commit -m "feat(dashboard): modernize requests table and request detail"
```

---

### Task 7: Metrics and Telemetry pages

**Files:**
- Modify: `dashboard/frontend/src/pages/MetricsPage.tsx` (full rewrite)
- Modify: `dashboard/frontend/src/pages/TelemetryPage.tsx` (full rewrite)

- [ ] **Step 1: Rewrite `src/pages/MetricsPage.tsx`**

```tsx
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "../api";
import { Card, EmptyState, Skeleton } from "../ui";
import { colors } from "../theme";
import type { MetricSample } from "../types";

const tooltipStyle = {
  backgroundColor: colors.panel,
  border: `1px solid ${colors.panelBorder}`,
  borderRadius: 8,
  fontSize: 12,
} as const;

export default function MetricsPage() {
  const [samples, setSamples] = useState<MetricSample[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const data = await api.series("guardrails_nonstream");
        if (alive) {
          setSamples(data);
          setError(null);
          setLoaded(true);
        }
      } catch (e) {
        if (alive) {
          setError((e as Error).message);
          setLoaded(true);
        }
      }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  // one series per (metric name + label signature)
  const series = useMemo(() => {
    const groups = new Map<string, MetricSample[]>();
    for (const s of samples) {
      const labelSig = Object.entries(s.labels)
        .map(([k, v]) => `${k}=${v}`)
        .join(",");
      const key = labelSig ? `${s.name}{${labelSig}}` : s.name;
      const list = groups.get(key) ?? [];
      list.push(s);
      groups.set(key, list);
    }
    return [...groups.entries()].map(([name, points]) => ({
      name,
      points: points.map((p) => ({ time: new Date(p.ts).toLocaleTimeString(), value: p.value })),
    }));
  }, [samples]);

  return (
    <div>
      <p style={{ fontSize: 13, color: colors.muted, marginTop: 0 }}>
        Time series scraped from the guardrails Prometheus exporter. Shows the
        exported admission-queue instruments (refreshes every 5 seconds).
      </p>
      {error && <p style={{ color: colors.red }}>{error}</p>}
      {!loaded && <Skeleton height={220} />}
      {loaded && !error && samples.length === 0 && (
        <Card>
          <EmptyState
            title="No samples yet"
            hint="Start the dashboard with --prom-url pointing at the guardrails metrics exporter and generate some traffic."
          />
        </Card>
      )}
      {series.map((s) => (
        <Card key={s.name} title={<span style={{ fontFamily: "monospace", fontSize: 13 }}>{s.name}</span>} style={{ marginBottom: 16 }}>
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer>
              <LineChart data={s.points}>
                <CartesianGrid stroke="#1f1f1f" strokeDasharray="3 3" />
                <XAxis dataKey="time" stroke={colors.muted} tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} stroke={colors.muted} tick={{ fontSize: 11 }} />
                <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: colors.muted }} />
                <Legend />
                <Line type="monotone" dataKey="value" dot={false} stroke={colors.green} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Rewrite `src/pages/TelemetryPage.tsx`**

```tsx
import { useEffect, useState } from "react";

import { api } from "../api";
import { Card, EmptyState, Skeleton } from "../ui";

const COLUMNS = [
  "event",
  "timestamp",
  "sessionId",
  "nemoguardrailsVersion",
  "railsEngine",
  "deploymentType",
  "numRailsConfigured",
  "numCustomFlows",
  "tracingEnabled",
  "streamingConfigured",
];

export default function TelemetryPage() {
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .telemetryEvents()
      .then((d) => {
        setEvents(d.items);
        setLoaded(true);
      })
      .catch((e) => {
        setError((e as Error).message);
        setLoaded(true);
      });
  }, []);

  return (
    <div>
      <p style={{ fontSize: 13, color: "#9d9d9d", marginTop: 0 }}>
        Anonymous usage events from the local audit file
        (~/.config/nemoguardrails/usage_stats.json). Read-only; newest last.
      </p>
      {error && <p style={{ color: "#ff5c5c" }}>{error}</p>}
      {!loaded && <Skeleton height={120} />}
      {loaded && events.length === 0 && !error && (
        <Card>
          <EmptyState title="No telemetry events found" hint="Events appear after guardrails runs locally." />
        </Card>
      )}
      {events.length > 0 && (
        <Card>
          <table className="nv-table">
            <thead>
              <tr>
                {COLUMNS.map((c) => (
                  <th key={c}>{c}</th>
                ))}
                <th>railTypesInUse</th>
                <th>llmProviders</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e, i) => (
                <tr key={i}>
                  {COLUMNS.map((c) => (
                    <td key={c}>
                      {c === "timestamp"
                        ? e[c] != null
                          ? new Date(Number(e[c]) * 1000).toLocaleString()
                          : ""
                        : String(e[c] ?? "")}
                    </td>
                  ))}
                  <td>{Array.isArray(e.railTypesInUse) ? (e.railTypesInUse as string[]).join(", ") : ""}</td>
                  <td>{Array.isArray(e.llmProviders) ? (e.llmProviders as string[]).join(", ") : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify build and tests**

Run: `cd dashboard/frontend && npm run build && npx vitest run`
Expected: build succeeds, all tests pass.

- [ ] **Step 4: Commit**

```bash
git add dashboard/frontend/src/pages/MetricsPage.tsx dashboard/frontend/src/pages/TelemetryPage.tsx
git commit -m "feat(dashboard): modernize metrics and telemetry pages"
```

---

### Task 8: Console page

**Files:**
- Modify: `dashboard/frontend/src/pages/ConsolePage.tsx` (full rewrite)

- [ ] **Step 1: Rewrite `src/pages/ConsolePage.tsx`**

```tsx
import { useEffect, useRef, useState, type CSSProperties } from "react";

import { api, extractSseText } from "../api";
import { RailBars } from "../components";
import { Button, Card, JsonBlock, Spinner, toast } from "../ui";
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
```

- [ ] **Step 2: Verify build and tests**

Run: `cd dashboard/frontend && npm run build && npx vitest run`
Expected: build succeeds, all tests pass.

- [ ] **Step 3: Commit**

```bash
git add dashboard/frontend/src/pages/ConsolePage.tsx
git commit -m "feat(dashboard): modernize console page with labels, primary action, toasts"
```

---

### Task 9: Challenges and Admin pages

**Files:**
- Modify: `dashboard/frontend/src/pages/ChallengesPage.tsx` (full rewrite)
- Modify: `dashboard/frontend/src/pages/AdminPage.tsx` (full rewrite)

- [ ] **Step 1: Rewrite `src/pages/ChallengesPage.tsx`**

```tsx
import { useEffect, useState } from "react";

import { api } from "../api";
import { StatusPill } from "../components";
import { Button, Card, JsonBlock, toast } from "../ui";
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
```

- [ ] **Step 2: Rewrite `src/pages/AdminPage.tsx`**

```tsx
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
```

- [ ] **Step 3: Verify build and tests**

Run: `cd dashboard/frontend && npm run build && npx vitest run`
Expected: build succeeds, all tests pass.

- [ ] **Step 4: Commit**

```bash
git add dashboard/frontend/src/pages/ChallengesPage.tsx dashboard/frontend/src/pages/AdminPage.tsx
git commit -m "feat(dashboard): modernize challenges and admin pages with toasts and cards"
```

---

### Task 10: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Build and run the full frontend test suite**

Run: `cd dashboard/frontend && npm run build && npx vitest run`
Expected: build succeeds; all tests pass (`api.test.ts` 3, `components.test.tsx` 4, `ui.test.tsx` 6).

- [ ] **Step 2: Pre-commit on all changed files**

Run from repo root:

```bash
uv run --locked pre-commit run --files \
  dashboard/frontend/index.html \
  dashboard/frontend/src/theme.ts \
  dashboard/frontend/src/ui.tsx \
  dashboard/frontend/src/ui.test.tsx \
  dashboard/frontend/src/components.tsx \
  dashboard/frontend/src/App.tsx \
  dashboard/frontend/src/pages/OverviewPage.tsx \
  dashboard/frontend/src/pages/RequestsPage.tsx \
  dashboard/frontend/src/pages/RequestDetail.tsx \
  dashboard/frontend/src/pages/MetricsPage.tsx \
  dashboard/frontend/src/pages/TelemetryPage.tsx \
  dashboard/frontend/src/pages/ConsolePage.tsx \
  dashboard/frontend/src/pages/ChallengesPage.tsx \
  dashboard/frontend/src/pages/AdminPage.tsx
```

Expected: all hooks pass.

- [ ] **Step 3: Browser smoke check**

The dashboard is already running on http://localhost:8500 serving `dist` (rebuilt in Step 1). Verify with Playwright: navigate to `/`, `/#/requests`, `/#/metrics`, `/#/telemetry`, `/#/console`, `/#/challenges`, `/#/admin` and screenshot at least Overview and Requests. Expect: no console errors besides none; pages render with the new shell.

- [ ] **Step 4: Push**

```bash
git push fork develop
```

Expected: push succeeds.

---

## Self-Review Notes

- Spec coverage: tokens/global CSS (T1), shared components + toasts (T2), restyled pills/tags/JSON (T3), shell with grouped nav, top bar, health pill, page actions (T4), Overview (T5), Requests + detail (T6), Metrics + Telemetry (T7), Console (T8), Challenges + Admin (T9), verification (T10). All spec sections covered.
- Type consistency: `Card`, `Button`, `EmptyState`, `Skeleton`, `Spinner`, `toast`, `Toaster` are defined in T2 and used from T4 onward. `usePageActions` is defined in T4 and used in T5. `colors`/`cardStyle` from `theme.ts` (T1) used throughout. `tooltipStyle` is redefined locally in OverviewPage and MetricsPage (kept local, not shared, per YAGNI).
- `StatusPill` text stays uppercase-transformed content but the React text node keeps lowercase; existing tests assert lowercase text and still pass because `text-transform` does not change the DOM text.
- Pages that previously kept an `error` state continue to render inline errors; action errors (console run, challenge run, admin reload, config load failures) now surface as toasts per spec.
