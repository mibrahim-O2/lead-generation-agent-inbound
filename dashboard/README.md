# Dashboard

A static React + TypeScript (Vite) page for reviewing leads: a table with score,
route and status, the drafted reply for each lead, run history, today's counts
and the average score.

It never sends anything. "Approve" only records a decision.

## Two modes

The mode is fixed when the site is built.

| Mode | When | What it does |
| --- | --- | --- |
| **Demo** | `VITE_API_URL` is not set | Shows bundled fictional data, labelled "Demo data". Makes no network requests. Buttons only change the page. This is what GitHub Pages serves. |
| **Local** | `VITE_API_URL` is set | Talks to the local API (`make serve`). Buttons save your decision to the local data. Refreshes every 5 seconds. |

`VITE_*` values are baked into the public JavaScript. Never put a key or any
secret in one. The API URL is not a secret.

## Commands

Run these from the repo root. They need Node.js 20 or newer.

| Command | What it does |
| --- | --- |
| `make dashboard-install` | Install the npm packages (once). |
| `make dashboard-dev` | Local mode at http://localhost:5173, talking to http://127.0.0.1:8000. Start `make serve` in another terminal first. |
| `make dashboard-demo` | Demo mode at http://localhost:5173. No API needed. |
| `make dashboard-test` | Type check and unit tests. |
| `make dashboard-build` | Production build of the demo site into `dashboard/dist/`. |
| `make dashboard-demo-data` | Regenerate `src/demo-data.json` from the mock model. |

To point local mode at another address:

```bash
make dashboard-dev API_URL=http://127.0.0.1:9000
```

The API only accepts requests from the origins in `CORS_ORIGINS` (default
`http://localhost:5173`), so open the dashboard at exactly that address.

## GitHub Pages

`.github/workflows/pages.yml` builds the demo site and deploys it to GitHub
Pages on every push to `main` that touches `dashboard/`. It sets `VITE_BASE` to
`/<repository name>/`, the path a project site is served from, and does not set
`VITE_API_URL`, so the published site is always in demo mode.

One-time setup in the GitHub repository: **Settings**, **Pages**, and under
**Build and deployment** choose **GitHub Actions** as the source.

## Files

```
index.html            page shell
vite.config.ts        base path (VITE_BASE) and the React plugin
src/main.tsx          entry point
src/App.tsx           page layout, loading, refresh, review actions
src/components.tsx    tiles, leads table, lead detail, run history
src/data.ts           demo or local mode, loading data, review calls
src/stats.ts          counts, average, filters, formatting
src/types.ts          TypeScript copies of the Python record models
src/demo-data.json    bundled fictional data (generated, do not edit by hand)
src/styles.css        styles, light and dark
scripts/make_demo_data.py   regenerates the demo data
```
