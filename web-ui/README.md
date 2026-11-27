# Web UI

**Design: "Aurora".** Dark navigation rail with searchable projects, calm workspace, an AI composer docked
at the bottom (pick a requirement, paste code, send), floating run bar for selected tests, live run stepper,
AI explanations as assistant replies, light/dark theme toggle, responsive down to phone width. Tokens and
components: `src/styles.css`, `src/components/ui.tsx`, `src/components/icons.tsx` (inline SVG, no icon font).

React 19 + TypeScript + Vite single-page app, served by Nginx in Docker (C4 container "Web UI"). It talks
**only** to `/api` on the Core Backend — never to the AI service or RabbitMQ (M2 §3.1). It holds no business
rules: role checks here only hide buttons; the Core Backend enforces them.

## Screens → use cases

| Route | Screen | Use case / FR |
|---|---|---|
| `/login` | Sign in (demo account shortcuts) | A-04 |
| `/projects` | List and create projects (Python · pytest) | UC-1 · FR-01 |
| `/projects/:id` | Requirements; AI test generation (+ optional code under test); manual tests; test list with status/version; run approved tests; recent runs; coverage, rule-based risks, quality report | UC-1..UC-4 · FR-02, 03, 06, 10, 11, 12 |
| `/tests/:id` | Read / edit code (new version → DRAFT), approve or reject **this version**, flag issues | UC-2 · FR-04, FR-05 |
| `/executions/:id` | Polls every 2 s until terminal; real runner results per test; logs; "Explain with AI" shown as a labelled hypothesis next to the evidence | UC-3 · FR-07, 08, 09 |

Quality attributes visible in the UI: AI output is always labelled (C-10); an AI outage shows a clear
message while everything else keeps working (QAS-2, T26); only APPROVED tests can be selected to run (C-04);
an INTERRUPTED run states that nothing was recorded as passed (QAS-7).

## Code map

| Path | Responsibility |
|---|---|
| `src/api/client.ts`, `src/api/types.ts` | Typed client for contract I1, uniform error → `ApiError`, user-facing error text |
| `src/auth.tsx` | Session (JWT in `sessionStorage`), sign-out on 401 |
| `src/permissions.ts` | Mirror of the role matrix (docs/phase1/03 §3) |
| `src/pages/*.tsx` | One file per screen |
| `src/components/ui.tsx` | Layout, status pills, AI badge, error banner, data-loading hook |
| `nginx.conf` | Serves the build and proxies `/api` → `core-backend:8000` (no other upstream) |

## Run

```bash
npm install
npm run dev          # http://localhost:5173, proxies /api to http://localhost:8000 (API_TARGET to change)
npm test             # 16 component/unit tests (Vitest + Testing Library), no backend needed
npm run typecheck
npm run build        # production build in dist/
```

In Docker Compose the `Dockerfile` builds the app and serves it with Nginx on port 80 (published as 8080).

## Verified end to end (Phase 2)

Against the real Core Backend and AI service (mock provider), in the browser: login → open project →
generate 3 AI tests with pasted code → review / edit (v2, back to DRAFT) / approve → run 3 approved tests →
page polls QUEUED → FAILED with per-test results and pytest stdout → AI explanation labelled as hypothesis.
With the AI service stopped, generation shows the "AI unavailable" message and the rest of the page works.
The run itself was executed by a stand-in for the Runner Worker (Docker not available on the dev machine).
