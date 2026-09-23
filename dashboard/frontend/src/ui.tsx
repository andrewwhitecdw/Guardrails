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
          {title && <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{title}</h3>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

type ButtonVariant = "primary" | "secondary" | "danger";

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

export function Button({
  variant = "secondary",
  style,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
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

export function resetToastsForTests() {
  toasts = [];
  nextToastId = 1;
  emitToasts();
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
    <div
      style={{
        position: "fixed",
        right: 16,
        bottom: 16,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        zIndex: 100,
      }}
    >
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
