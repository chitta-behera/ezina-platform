# Ezina Connect – WhatsApp farmer registration

AI-assisted WhatsApp onboarding for the Ezina platform. **Python owns the workflow; Claude owns the language.**

```
Meta ─POST /webhook─▶ verify HMAC ─▶ parse ─▶ INSERT messages (unique wa_message_id) ─▶ 200 OK
                                                  │  background task (+ re-run at startup for unfinished rows)
                                                  ▼
   per-farmer lock (asyncio lock + pg_advisory_xact_lock) ─▶ oldest pending message (by WhatsApp timestamp)
                                                  ▼
   ConversationService
     ├─ opt-out / handoff / rate-limit / unsupported types
     ├─ buttons, location, photos  → handled by Python only (no model call)
     └─ text → ClaudeService (one forced tool → AIResponse) → intent_router → validators
                → state machine picks the next stage → reply_guard → Claude text OR safe template
                                                  ▼
   reply rows written to the outbox (messages.status = queued) in the SAME transaction as the state change
   COMMIT ─▶ flush outbox ─▶ Graph API (retry/backoff, 24h-window check, template fallback) ─▶ wamid saved
```

* **Claude never writes anything.** It has a single tool (`record_interpretation`) used only to get guaranteed JSON.
  Every extracted value is validated in Python before it is saved; Claude's reply is checked by `workflows/reply_guard.py`
  (claims of verification, promises of buyers/income, requests for ID/bank/OTP/typed coordinates, re-asking collected
  data). Failing replies are replaced by templates.
* **Registration status and verification status are separate fields** on the farmer. Only the admin endpoint can
  verify; confirmation sets `SUBMITTED` + `PENDING` and opens a `verifications` row.
* **No personal data is stored before consent.** Answers collected during the flow live in `conversations.draft`
  (JSONB) and become `farmers/farms/farmer_crops` rows only when the farmer confirms the summary.
* **Durability:** inbound rows are committed before the 200; unfinished rows (`received`/`processing`) are re-processed at
  startup. Replies use an outbox, so a crash can't lose or double-send a reply.

## Layout

```
ezina-connect/app/
  main.py config.py database.py logging_config.py enums.py
  api/        webhook.py whatsapp.py (internal send) admin.py dependencies.py
  services/   whatsapp_service claude_service conversation_service message_processor
              farmer_service media_service storage_service rate_limiter ops_notifier container
  workflows/  state_machine farm_flow farmer_registration intent_router validators reply_guard messages
  models/ schemas/ prompts/farmer_assistant.txt
ezina-connect/migrations/   Alembic        ezina-connect/tests/   pytest (+ fixtures/ sample Meta payloads)
```

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                        # fill in values
cd ezina-connect
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

# C:\Users\chitt\AppData\Local\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe http 8000

With no `DATABASE_URL`, a local SQLite file is used so you can try things quickly. For real use point `DATABASE_URL` at
PostgreSQL (Neon / Supabase pooled strings such as `postgresql://…?sslmode=require` are accepted as-is; they are
rewritten for asyncpg and prepared-statement caching is disabled for PgBouncer).

Docker: `docker build -t ezina-connect . && docker run --env-file .env -p 8000:8000 ezina-connect`
(runs `alembic upgrade head`, then Uvicorn on `$PORT`).

## Connect Meta WhatsApp Cloud API

1. Meta for Developers → create an app (type *Business*) → add the **WhatsApp** product.
2. *WhatsApp → API Setup*: copy the **temporary access token** (or create a System User token for production),
   **Phone number ID** and **WhatsApp Business Account ID** into `.env`. Add your own number as a verified *recipient*.
3. *App settings → Basic*: copy **App Secret** → `META_APP_SECRET` (used to verify `X-Hub-Signature-256`).
4. Expose your server: `ngrok http 8000` (or `cloudflared tunnel --url http://localhost:8000`).
5. *WhatsApp → Configuration → Webhook → Edit*: Callback URL `https://<tunnel>/webhook`, Verify token = your
   `WHATSAPP_VERIFY_TOKEN`. Meta calls `GET /webhook` and must get the challenge back.
6. Under **Webhook fields**, **subscribe to `messages`** (this delivers both messages and delivery statuses).
7. Send a WhatsApp message from your verified phone to the test number. You should get the Ezina welcome.

Troubleshooting: `401` on POST → wrong `META_APP_SECRET`; `403` on verification → token mismatch; no replies and a
`token rejected` CRITICAL log → access token expired (the temporary token lasts ~24h).
Replying outside the 24h window needs an approved template (see `WHATSAPP_TEMPLATE_VERIFICATION`).

## Try the API by hand

```bash
# send a message (inside the 24h window the farmer must have written to you in the last 24h)
curl -X POST localhost:8000/api/whatsapp/send -H "X-API-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
     -d '{"to":"+26771234567","text":"Hello from Ezina"}'
# list farmers awaiting verification
curl -H "X-API-Key: $ADMIN_API_KEY" "localhost:8000/api/admin/farmers?verification_status=PENDING"
# verify (notifies the farmer; uses the template if the 24h window is closed)
curl -X POST -H "X-API-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
     localhost:8000/api/admin/farmers/<id>/verification -d '{"status":"VERIFIED","notes":"Visited","reviewer":"ops1"}'
# release a human handoff
curl -X POST -H "X-API-Key: $ADMIN_API_KEY" localhost:8000/api/admin/farmers/<id>/handoff/release
```
The admin API and `/api/whatsapp/send` are **disabled (503) while `ADMIN_API_KEY` is empty**.

Replay a sample webhook without Meta (sign the body with your app secret):

```bash
BODY=$(sed 's/__WA_ID__/26771234567/;s/__MSG_ID__/wamid.TEST1/;s/__TS__/'$(date +%s)'/' ezina-connect/tests/fixtures/text.json)
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$META_APP_SECRET" | sed 's/^.* //')
curl -X POST localhost:8000/webhook -H "X-Hub-Signature-256: sha256=$SIG" -H "Content-Type: application/json" -d "$BODY"
```

## Tests

```bash
cd ezina-connect && pytest
```
Anthropic and Meta are mocked (scripted `FakeClaude`, `httpx.MockTransport`); the DB is a temporary SQLite file.
Covers: webhook verification/signatures, text/location/image/interactive/unsupported messages, media download+storage,
status callbacks (never regress), duplicates, out-of-order messages, startup recovery, intent routing, structured-output
validation/retry/fallback, validators, reply guard, the full registration run, multi-answer messages, corrections at
review, pause/resume after a day, typed address instead of a location pin, cancel, opt-out, handoff, 24h window +
template fallback, send retries / expired token, admin verification + notification, anonymisation, log masking.

## Behaviour notes / decisions

* **LangChain / LangGraph are intentionally not used.** The workflow is a small deterministic state machine plus one
  Anthropic SDK call; a framework would add indirection without helping. (Easy to add later if you need it.)
* **Retries:** Claude calls use the SDK's built-in exponential backoff (429 / 5xx / overloaded; `CLAUDE_MAX_RETRIES`).
  Invalid structured output is retried once, then Python falls back to a templated message.
* **Per-farmer ordering** uses an in-process lock plus `pg_advisory_xact_lock` (works behind PgBouncer transaction pooling).
* **Templated messages (consent, summary, buttons, fallbacks) are English-only.** Claude's conversational replies follow the
  farmer's language. Translate `workflows/messages.py` for each language you launch (especially the consent text).
* **Rate limiting is in-process** (`RATE_LIMIT_PER_MINUTE`); use Redis if you run several replicas.
* The initial Alembic revision creates all tables from the models; generate later revisions with `--autogenerate`
  against PostgreSQL.
* Model call latency happens inside the farmer's DB transaction (it holds the per-farmer lock). Fine at this scale;
  revisit if one farmer's slow turns must never hold a pooled connection.

## Status vs. the requested phases

| Phase | Item | State |
|---|---|---|
| 1 | Webhook, signatures, dedupe, durable processing, ordering | done |
| 1 | WhatsApp text / buttons / lists / images / templates, mark-as-read, retries, 24h window | done |
| 1 | Claude service (forced-tool structured output, caching, validation, fallback) | done |
| 1 | Registration state machine through submission, location + photo handling, models, migration | done |
| 2 | Admin endpoints, verification notifications, human handoff + release, status checks | done |
| 2 | `ADD_FARM` / `ADD_CROP` / `UPDATE_CROP` / `UPDATE_PROFILE` flows | **not yet** (routed to a polite "coming soon"; `farm_flow.py` is ready for reuse) |
| 3 | Harvest availability flow, opportunity notifications | **not yet** (`harvests` table and extraction fields exist) |
| 3 | Prompt-evaluation script (~30 messages against the real API) | **not yet** |

Not verified against a real PostgreSQL instance or the live Meta / Anthropic APIs (no credentials in this environment);
the test suite runs on SQLite with mocked HTTP. Run the manual end-to-end check above before going live.
