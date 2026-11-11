# Plaq Planner Prompt

Two planners are available:

## DeterministicPlanner (always on, auditable)

Keyword → fixed plan:

- Bernstein-Vazirani / circuit synthesis → `quantum.compile` + `quantum.estimate` + `artifacts.publish`
- Pareto / benchmark / optimize / QEC → compile + estimate + `quantum.simulate` + publish
- QAOA / MaxCut → compile + `quantum.run` (energy) + estimate + publish
- chemistry / VQE / FeMoCo → compile + run + estimate
- threshold / surface code / MWPM → `quantum.simulate` + `quantum.threshold`
- Shor / RSA → compile + estimate
- clean / purge → `terminal.run` + `git.diff`
- pytest → `tests.run`

## LLMProvider (when `OPENAI_API_KEY` is set)

`generate_plan` calls an OpenAI-compatible chat endpoint (JSON mode, one retry)
and asks for JSON:

```json
{"steps":[{"step_name":"...","criteria":"...","tool_name":"...","tool_parameters":{}}]}
```

Unknown tool names are dropped; empty/invalid JSON falls back to DeterministicPlanner.
`verify_criteria` also asks the model for `{"ok": bool, "reason": "..."}`. A failed
tool (nonzero exit) can never be overridden to pass. Parse failure falls back
to the deterministic checker.

Environment:

- `OPENAI_API_KEY` — enable LLM provider
- `OPENAI_BASE_URL` — default `https://api.openai.com/v1`
- `PLAQ_MODEL` — default `gpt-4o`
- `PLAQ_LLM_PLANNING=off` — keep planning deterministic even with a key
