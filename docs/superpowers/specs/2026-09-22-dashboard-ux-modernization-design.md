# Guardrails Dashboard UX Modernization — Design

Date: 2026-09-22
Status: Approved
Scope: `dashboard/frontend` only. No backend, API, or routing changes.

## Goal

Make the admin dashboard look and feel like a modern web application while
keeping the NVIDIA dark branding established in c4dff0f5a. Visual direction:
dark pro dashboard. Scope: restyle + UX polish, no new features.

## Design system

New `src/theme.ts` exports design tokens:

- Colors: `bg: #0f0f0f`, `panel: #161616`, `border: #2a2a2a`,
  `text: #e8e8e8`, `muted: #9d9d9d`, `green: #76b900`, `red: #ff5c5c`,
  `amber: #f79009`.
- Shared style helpers for cards, page headers, and focus rings.

New shared components in `src/components.tsx` (or `src/ui.tsx` if it grows):

- `Card` — panel surface: `#161616` bg, `1px solid #2a2a2a` border, 8px
  radius, optional title row.
- `Button` — variants `primary` (green fill, black text), `secondary`
  (outlined), `danger` (red outline); hover darkens/elevates, disabled state.
- `Badge` / `StatusPill` (existing, restyled) — semantic colors, softer
  corners.
- `EmptyState` — icon + headline + guidance line (e.g. "No requests yet —
  send one from the Console").
- `Skeleton` and `Spinner` — for loading states on every page's initial
  fetch.
- Toast system — small module with `toast(message, kind)` and a `<Toaster/>`
  mounted in `App`; used for admin action results, console errors, and copy
  feedback, replacing bare status text.

## App shell

- Sidebar (slimmer, ~220px): NVIDIA mark + wordmark + subtitle kept; nav
  grouped with small uppercase section labels — *Monitor* (Overview,
  Requests, Metrics, Telemetry), *Tools* (Console, Challenges), *System*
  (Admin) — each item with an inline SVG icon; active item keeps the green
  pill treatment.
- Sticky top bar in the main column: page title on the left; on the right a
  server-health pill (dot + "healthy"/"down" + URL) and page-contextual
  controls (e.g. Overview's time-range `<select>` moves here).

## Pages

- **Overview**: stat cards become `Card`s with green top accent and larger
  numerals; charts keep green/red series with dark tooltip styling; the
  ingestion block becomes a compact card list.
- **Requests**: sticky table header, row hover, monospace request IDs,
  status badges, `EmptyState` when no records match, filters in a toolbar
  row.
- **RequestDetail**: detail layout on `Card`s with labeled sections.
- **Metrics**: metric picker and chart on cards; dark chart tooltip.
- **Telemetry**: table restyle consistent with Requests; empty state.
- **Console**: form gets labels and focus rings; Send button uses
  `Button primary`; responses render in `JsonBlock`; errors surface as
  toasts.
- **Challenges**: cards for challenges with clear approve/deny affordances
  and toast feedback.
- **Admin**: action buttons use variants; the admin-hook warning banner is
  a styled amber banner; status block uses badges.

Global: form controls get a green focus ring (`outline: 2px solid rgba(118,
185, 0, 0.5)`), consistent heights, and the existing dark control style from
`index.html` is kept.

## Error handling

Unchanged data flow; errors that were shown as inline text now also (or
instead, for actions) surface as error toasts. Loading and error states are
distinct on every page.

## Testing

- Existing vitest suites (`api.test.ts`, `components.test.tsx`) must pass;
  extend `components.test.tsx` with render checks for the new shared
  components (Button variants, Badge, EmptyState, Skeleton).
- `npm run build` succeeds.
- Pre-commit passes on changed files.
- Manual verification: Playwright screenshots of all seven routes served by
  the running dashboard on :8500.

## Non-goals

- No routing, backend, or API changes; no new data features (no URL-state
  filters, no keyboard shortcuts); no chart library changes; no
  code-splitting work (the 500 kB chunk warning is pre-existing).
