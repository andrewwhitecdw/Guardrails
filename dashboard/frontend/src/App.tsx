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
