import { HashRouter, NavLink, Route, Routes } from "react-router-dom";

import AdminPage from "./pages/AdminPage";
import ChallengesPage from "./pages/ChallengesPage";
import ConsolePage from "./pages/ConsolePage";
import MetricsPage from "./pages/MetricsPage";
import OverviewPage from "./pages/OverviewPage";
import RequestsPage from "./pages/RequestsPage";
import TelemetryPage from "./pages/TelemetryPage";

const NAV: [string, string][] = [
  ["/", "Overview"],
  ["/requests", "Requests"],
  ["/metrics", "Metrics"],
  ["/telemetry", "Telemetry"],
  ["/console", "Console"],
  ["/challenges", "Challenges"],
  ["/admin", "Admin"],
];

const NV_GREEN = "#76b900";

function NvidiaMark() {
  return (
    <svg viewBox="0 0 100 100" width={30} height={30} aria-hidden="true">
      <g fill="none" stroke={NV_GREEN} strokeWidth={8} strokeLinecap="round">
        <path d="M18 50 A32 32 0 0 1 82 50" />
        <path d="M31 50 A19 19 0 0 1 69 50" />
        <path d="M44 50 A6 6 0 0 1 56 50" />
        <path d="M18 63 A32 32 0 0 0 82 63" opacity={0.55} />
        <path d="M31 63 A19 19 0 0 0 69 63" opacity={0.55} />
      </g>
    </svg>
  );
}

export default function App() {
  return (
    <HashRouter>
      <div
        style={{
          display: "flex",
          minHeight: "100vh",
          fontFamily: "'Segoe UI', system-ui, sans-serif",
          color: "#e8e8e8",
          background: "#0f0f0f",
        }}
      >
        <nav
          style={{
            width: 210,
            background: "#000000",
            borderRight: "1px solid #2a2a2a",
            padding: "16px 14px",
            flexShrink: 0,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <NvidiaMark />
            <span style={{ fontSize: 20, fontWeight: 700, letterSpacing: 2, color: "#ffffff" }}>
              NVIDIA
            </span>
          </div>
          <div
            style={{
              fontSize: 11,
              color: NV_GREEN,
              textTransform: "uppercase",
              letterSpacing: 1.5,
              margin: "0 0 20px 40px",
            }}
          >
            Guardrails Dashboard
          </div>
          {NAV.map(([to, label]) => (
            <div key={to} style={{ marginBottom: 4 }}>
              <NavLink
                to={to}
                style={({ isActive }) => ({
                  display: "block",
                  textDecoration: "none",
                  color: isActive ? "#000000" : "#9d9d9d",
                  background: isActive ? NV_GREEN : "transparent",
                  fontWeight: isActive ? 600 : 400,
                  borderRadius: 4,
                  padding: "6px 10px",
                  fontSize: 14,
                })}
              >
                {label}
              </NavLink>
            </div>
          ))}
        </nav>
        <main style={{ flex: 1, padding: 24, overflow: "auto" }}>
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/requests" element={<RequestsPage />} />
            <Route path="/metrics" element={<MetricsPage />} />
            <Route path="/telemetry" element={<TelemetryPage />} />
            <Route path="/console" element={<ConsolePage />} />
            <Route path="/challenges" element={<ChallengesPage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Routes>
        </main>
      </div>
    </HashRouter>
  );
}
