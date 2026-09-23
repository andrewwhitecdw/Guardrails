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
