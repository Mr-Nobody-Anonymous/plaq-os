# plaq-api

FastAPI application server for Plaq-OS. Exposes REST (`/api/v1/*`),
WebSocket (`/ws/stream`), SSE (`/api/v1/events/stream`), and serves the
workbench UI from `apps/workbench/`.

## Run

```bash
pip install -e ./apps/api -e ./packages/contracts -e ./packages/sdk-python \
  -e ./services/control-plane -e ./services/agent-runtime \
  -e ./services/sandbox-manager -e ./services/model-gateway \
  -e ./services/artifact-service -e ./engines/quantum
uvicorn plaq_api.app:app --host 127.0.0.1 --port 8000
```

Or via the unified CLI: `python plaq.py serve --port 8000`.

## Env

- `PLAQ_DB_PATH` — SQLite path (default `~/.plaq/plaq.db`)
- `PLAQ_CORS_ORIGINS` — comma-separated CORS allow-list
- `PLAQ_API_KEY` — Bearer token; generated at `~/.plaq/api_key` on `plaq serve` if unset
- `PLAQ_AUTH=off` — disable API-key auth
- `OPENAI_API_KEY` / `PLAQ_MODEL` / `OPENAI_BASE_URL` — LLM planner

New endpoints: `POST /api/v1/quantum/run|simulate|threshold|qasm`,
`GET /api/v1/quantum/workloads|hardware`,
`POST /api/v1/tasks/{id}/run`, `GET /api/v1/jobs`.
