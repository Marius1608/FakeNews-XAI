# FakeNews-XAI — Frontend

React 19 + TypeScript + [Vite](https://vite.dev) + Material UI 9.

## Development

```bash
npm ci
echo "VITE_API_URL=http://localhost:8000" > .env   # backend URL for local dev
npm run dev                                         # http://localhost:3000
```

The dev server runs on port 3000 (`strictPort`), the origin allowed by the backend's default `CORS_ORIGINS`.

## Scripts

| Script | What it does |
|---|---|
| `npm run dev` / `npm start` | Vite dev server with hot reload on :3000 |
| `npm run build` | Type-check (`tsc --noEmit`) and production build into `build/` |
| `npm run preview` | Serve the production build locally |
| `npm run typecheck` | Type-check only |

## Production

`VITE_API_URL` is left unset in the Docker build, so the app calls the API on the same origin. FastAPI serves `build/` (assets under `/assets`) on HuggingFace Spaces — see the root `README.md`.

## Structure

- `src/App.tsx` — sidebar layout, light/dark toggle, lazy-loaded tabs
- `src/components/` — tabs and result views
- `src/theme/` — color schemes (light + dark) and helpers
- `src/api/client.ts` — typed API client
- `src/data/examples.ts` — example articles
