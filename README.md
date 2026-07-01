# HealthSense AI

Agentic health-assistant portfolio project. Multi-agent orchestration over a
FastAPI service, with a memory layer, a safety/guardrails layer, and an
evaluation layer added across phases.

## Stack
- **API:** FastAPI
- **Agents:** CrewAI + LangChain (Anthropic LLM)
- **Data:** SQLAlchemy ORM — SQLite by default, MySQL by changing one env var
- **Tests:** pytest

## Structure
```
healthsense-ai/
├── config/settings.py        # typed settings via pydantic-settings
├── app/
│   ├── main.py               # FastAPI entrypoint, creates tables on startup
│   ├── api/routes.py         # /health and /consult endpoints
│   ├── agents/               # CrewAI crew, agents, tasks  (Phase 1)
│   ├── core/llm.py           # LLM factory (lazy import)
│   ├── db/                   # SQLAlchemy engine, session, ORM models
│   ├── memory/memory.py      # conversation memory interface  (Phase 1)
│   ├── safety/guardrails.py  # risk screening interface       (Phase 2)
│   └── schemas/schemas.py    # request/response models
└── tests/test_health.py
```

## Run it
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # then fill in ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs

## Phase map
- **Phase 0 (now):** this scaffold — boots, health check, DB connected, stubs in place.
- **Phase 1:** flesh out `agents/`, wire real CrewAI crew, implement `memory/`.
- **Phase 2:** implement `safety/guardrails.py` (NeMo Guardrails), add evaluation + LLMOps tracing.
- **Phase 3:** deploy + narrative.

> Note: agent files contain the CrewAI structure but are *stubbed* so the app
> boots before keys/deps are configured. The `/consult` endpoint runs the
> safety → crew → memory pipeline once you fill those in.
