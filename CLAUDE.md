# Ezina Connect

WhatsApp farmer registration and engagement for Ezina, a buyer-led agricultural sourcing and farmer verification
platform. FastAPI backend, Meta WhatsApp Cloud API for messaging, Anthropic Claude for language understanding,
PostgreSQL (Neon/Supabase, async SQLAlchemy) for all state. The app lives in `ezina-connect/`.

**Always follow `docs/ezina-spec.md`. Read it before making changes.**

The marketing website (www.ezina.ai) is a separate pnpm/Next.js workspace in `ezina-web/`, with its own rules in
`ezina-web/CLAUDE.md` and its spec in `ezina-web/docs/website-spec.md`. The backend rules below don't apply to it.
Current status, known issues, pending work and decisions are in `docs/progress.md`.

## Architecture rules (do not break)

- **Python owns the workflow.** A deterministic state machine (`app/workflows/state_machine.py`) decides the stage,
  the next field, completion and every status transition.
- **Claude only interprets language and drafts replies.** It never writes to the database, never changes state, and
  never decides that registration is complete or verified. It has one tool (`record_interpretation`) used only to get
  structured output.
- **Python validates every extracted value** (`workflows/validators.py`) and checks every Claude reply
  (`workflows/reply_guard.py`) before sending; on failure use a templated message (`workflows/messages.py`).
- **Never auto-verify farmers.** Only the admin endpoint (`ADMIN_API_KEY`) can set a verification status.
- **No personal data is stored before consent.** Answers live in `conversations.draft` until the farmer confirms.
- **No LangChain / LangGraph / agent frameworks, no message brokers or extra microservices.**
- Registration status and verification status are separate farmer fields, not conversation stages.
- Location comes only from the WhatsApp location pin. Never ask farmers to type GPS coordinates.
- Replies are written to the outbox (`messages.status = queued`) in the same transaction as the state change and
  sent after commit. Do not send WhatsApp messages from inside business logic directly.

## Commands (run from `ezina-connect/`, venv at `../.venv`)

```bash
# setup
python -m venv ../.venv && ../.venv/Scripts/pip install -r ../requirements.txt   # Windows venv path
# run
../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
# tests (mocked Meta + Claude, temp SQLite; no credentials needed)
../.venv/Scripts/python -m pytest -q
# migrations
../.venv/Scripts/python -m alembic upgrade head
../.venv/Scripts/python -m alembic revision --autogenerate -m "describe change"   # run against PostgreSQL
../.venv/Scripts/python -m alembic downgrade -1
```

Remote testing: `ngrok http 8000`, set the Meta webhook to `https://<tunnel>/webhook` (see `README.md`).
Beware shell variables `ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY`: environment variables override `.env`.

## Conventions

- Layout: `app/api` (routers, auth deps) · `app/services` (I/O and orchestration) · `app/workflows` (pure,
  deterministic logic) · `app/models` (SQLAlchemy) · `app/schemas` (Pydantic) · `app/prompts` · `migrations/` · `tests/`.
- Everything is `async` (SQLAlchemy 2.x async, httpx, Anthropic async client). Python 3.12, type hints, Pydantic v2.
- Logging: stdlib `logging` with `logging.getLogger("ezina.<area>")`, structured fields via `extra=`.
  Mask phone numbers with `mask_phone()`; never log tokens, keys or message bodies containing personal data.
- No secrets in code or git. All config via `app/config.py` (pydantic-settings); document new variables in
  `.env.example` with placeholders only.
- Use `Edit`-style small changes; keep new workflow logic in `app/workflows` and cover it with tests.
- Tests: pytest + pytest-asyncio, scripted `FakeClaude` and `httpx.MockTransport` (see `tests/conftest.py`).
  Add or update tests with every behaviour change; the full suite must pass.
- Optional steps (location, farm photo, crop photo) are all asked the same way: 📎 instruction + one
  "Skip for now" button.

## After every task

**After completing any task, update `docs/progress.md`** (phases, what works, known issues, pending tasks, decisions).
