# ChainScope X

**Effect-Aware Capability Intelligence Engine** — a portable, remote-first project for testing and analyzing tool-using AI agents. The repository is currently at the R0 foundation checkpoint; it is not the finished security platform.

## Current scope

R0 provides a minimal FastAPI app, a responsive local landing page, a liveness endpoint, basic unit tests, and project governance/recovery documents. No tool execution, security analysis, database, authentication, RAG, LangGraph, or external service integration is implemented.

## Run locally

Python 3.12+ is recommended for this starter. FastAPI, Jinja2, and Uvicorn must be available in the environment. To create an isolated environment and install the small pinned dependency set:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`; health response is at `/health`. The app binds to localhost in this example. Do not expose it publicly.

## Project memory

See `docs/PROJECT_STATE.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/DECISION_LOG.md`, and `docs/RESTORE_GUIDE.md`. The project phases are gated: R1 has not started and requires explicit review/approval. The Galaxy Tab target has not been inspected or tested.
