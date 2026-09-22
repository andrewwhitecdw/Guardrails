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

export default function App() {
  return (
    <HashRouter>
      <div style={{ display: "flex", minHeight: "100vh", fontFamily: "system-ui, sans-serif", color: "#202124" }}>
        <nav style={{ width: 190, borderRight: "1px solid #dadce0", padding: "16px 12px", flexShrink: 0 }}>
          <h2 style={{ fontSize: 16, margin: "0 0 16px" }}>Guardrails</h2>
          {NAV.map(([to, label]) => (
            <div key={to} style={{ marginBottom: 6 }}>
              <NavLink
                to={to}
                style={({ isActive }) => ({
                  textDecoration: "none",
                  color: isActive ? "#1a73e8" : "#5f6368",
                  fontWeight: isActive ? 600 : 400,
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
