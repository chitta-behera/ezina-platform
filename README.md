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
ezina_id_verify/  ID verification (AWS Rekognition): name extraction + face match; ezina_id_verify/tests/  pytest
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

## ID verification (`ezina_id_verify/`)

`ezina_id_verify` does two independent checks with AWS Rekognition: **name extraction** (a document type and an ID image in,
the cardholder's full name out) and **face match** (the face on the ID versus a selfie). It is a Python package that other
modules (such as ezina-connect) import directly, with an optional HTTP wrapper. **JPEG and PNG only**: the type is detected
from the image bytes, never from a file name or content type. It is **not wired into ezina-connect yet**.

### Install

```bash
pip install -e .            # from the repo root, into the same venv as ezina-connect
pip install -e ".[api]"     # + the optional HTTP wrapper (python-multipart is also in requirements.txt)
pip install -e ".[llm]"     # + the optional LLM fallback (anthropic is also in requirements.txt)
```

### Use

```python
from ezina_id_verify import (
    extract_name, NameResult, match_face, FaceMatchResult,
    UnsupportedDocType, UnsupportedFile, RekognitionServiceError,
)

name = await extract_name("passport", id_bytes)        # NameResult
face = await match_face(id_bytes, selfie_bytes)        # FaceMatchResult
```

```python
name.found, name.full_name   # True, "CHITTA RANJAN BEHERA"  (name.name is the same, for clients that read "name")
name.given_names, name.surname, name.method, name.confidence, name.warnings   # method: mrz | label | layout | llm
face.verified, face.similarity, face.confidence_band   # similarity 0-100; band: match | possible_match | no_match
face.face_found_id, face.face_found_selfie, face.liveness_passed, face.warnings
```

"Name not found", "no face found" and "faces do not match" are **results** (`found=False`, `face_found_selfie=False`,
`verified=False`), not exceptions. Exceptions: `UnsupportedDocType` (not in `documents.yaml`), `UnsupportedFile` (not
JPEG/PNG, empty, unreadable, over `MAX_UPLOAD_MB`) and `RekognitionServiceError` (AWS failed after the retries, or with an error
retrying cannot fix). Calls run in a worker thread (`asyncio.to_thread`), so async callers are not blocked.

- `face_found_id` / `face_found_selfie` are `False` only when Rekognition positively reported no usable face. An image that was
  not examined (the selfie had no face, so the ID was never compared) keeps its flag `True`. When Rekognition rejects an image
  outright, `error` is `selfie_image_rejected` or `id_image_rejected`.
- `liveness_passed` is always `None`: Rekognition Face Liveness needs an in-app video session and cannot run on a WhatsApp
  photo (liveness is ezina-connect's selfie challenge).

### Document types

Configured in `ezina_id_verify/config/documents.yaml` (new types need only config):

| doc_type | Strategy order |
|---|---|
| `passport` (any ICAO passport) | MRZ, then printed Surname / Given names, then LLM |
| `aadhaar` (aliases `aadhar`, `aadhaar_masked`) | layout (name above the DOB line), then LLM |
| `pan` | label ("Name"), then layout (line below the header, old format), then LLM |
| `voter_id`, `driving_licence` | label, then LLM |
| `botswana_omang`, `kenya_id`, `south_africa_id`, `nigeria_nin`, `ghana_card` | label (surname + given names), then LLM |
| `generic_id` (unknown layout, best effort) | MRZ, label, first name-like line, then LLM |

The LLM step runs only if `LLM_FALLBACK_ENABLED=true` and every earlier strategy failed. It sends only the OCR lines (every
digit masked as `#`) and the `doc_type`, forces a tool call with a JSON schema, and rejects an answer that fails the name rules
or contains a word that is not on the document. Relatives' names (Father's / Husband's / Mother's Name, S/O, D/O, W/O, C/O,
S/D/W of) are never returned. Confidence: `mrz` 0.95; `label` 0.85 (minus 0.1 if the OCR line confidence is below 80);
`layout` 0.7; `llm` 0.6; minus 0.1 per warning; never below 0.

**Privacy:** only the name is returned. ID numbers, dates of birth, addresses, raw OCR text, face images and face coordinates
are never returned, logged or stored; logs hold only the check type, doc_type, outcome, confidence or similarity and timings.

### AWS and configuration

Credentials come from the standard AWS chain (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in the environment,
`~/.aws/credentials`, or an IAM role); a `.env` file does **not** export them to boto3. IAM needs
`rekognition:DetectText`, `rekognition:DetectFaces` and `rekognition:CompareFaces`. Throttling, 5xx and network errors are
retried with exponential backoff. Images are fixed for EXIF rotation and downscaled under Rekognition's 5 MB limit (at least
1000 px on the longer side).

Variables (see the "ID verification module" section of `.env.example`): `AWS_REGION`, `MAX_UPLOAD_MB`, `NAME_CASE`
(`upper` | `title` | `original`), `LLM_FALLBACK_ENABLED`, `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `FACE_MATCH_THRESHOLD`,
`FACE_POSSIBLE_MATCH_THRESHOLD`, `FACE_MIN_SHARPNESS`, `FACE_MIN_BRIGHTNESS`, `ID_VERIFY_API_KEY`, `LOG_LEVEL`; optional
`AWS_MAX_RETRIES`, `AWS_RETRY_BASE_DELAY`, `FACE_ID_MIN_WIDTH`, `ID_VERIFY_DOCUMENTS_CONFIG`. Invalid settings or a malformed
`documents.yaml` fail with a `ConfigError` naming the problem (the wrapper fails at startup; library callers on first use, or
call `ezina_id_verify.config.load_documents()` at startup).

### HTTP wrapper (optional)

```bash
uvicorn ezina_id_verify.api:app --port 8100       # needs: pip install -e ".[api]"
curl -X POST localhost:8100/extract-name -H "X-API-Key: $ID_VERIFY_API_KEY" -F doc_type=passport -F file=@passport.jpg
curl -X POST localhost:8100/match-face   -H "X-API-Key: $ID_VERIFY_API_KEY" -F id_image=@id.jpg -F selfie_image=@selfie.jpg
curl localhost:8100/health
docker build --target id-verify-api -t ezina-id-verify . && docker run -p 8100:8000 --env-file .env -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY ezina-id-verify
```

`200` for every normal result (including "not found" / "no match"); `400` for an unsupported `doc_type`, a PDF or other
non-JPEG/PNG upload, an oversized file or a malformed request; `502` when AWS Rekognition fails; `401` for a wrong key. The key
is the `X-API-Key` header (`ID_VERIFY_API_KEY`); if it is empty the API is open and a warning is logged at startup (local
development only). The wrapper passes only the uploaded bytes to the two functions and ignores the content type and file name.

### Adding a document type or label

Edit `documents.yaml` (the header explains every key) or point `ID_VERIFY_DOCUMENTS_CONFIG` at your own copy:

```yaml
documents:
  ethiopia_id:
    strategies: [label, llm]                       # tried in this order: mrz | label | layout | llm
    labels:
      full_name: ["full name", "nom complet"]      # or surname + given_names for separate fields
```

A new label spelling (including OCR variants) is just another entry: matching is case-insensitive and tolerates apostrophes,
spaces and "/"; the longest match on a line wins. Separate fields use `surname: [...]` plus `given_names: [[...], [...]]` (one
group per field, joined in order; full name = "given names surname"). Labels of relatives go in `skip_labels` (all documents)
or `labels.skip` (one); words that are never a name go in `stop_words` / `stop_phrases`. Write `no`, `yes`, `on`, `off` in
quotes in YAML, or YAML reads them as booleans. A typo, an unknown strategy or a missing section fails at load time with the
file path and the problem.

### Tuning the face thresholds

| Setting | Default | Effect |
|---|---|---|
| `FACE_MATCH_THRESHOLD` | 90 | similarity at or above: `verified=True`, band `match` |
| `FACE_POSSIBLE_MATCH_THRESHOLD` | 75 | at or above (and below the match threshold): band `possible_match` |
| `FACE_MIN_SHARPNESS` | 20 | selfie sharpness below this: warning `selfie_blurry` |
| `FACE_MIN_BRIGHTNESS` | 30 | selfie brightness below this: warning `selfie_dark` |
| `FACE_ID_MIN_WIDTH` | 0.06 | ID face narrower than this fraction of the image width: warning `small_face_id` |

`CompareFaces` is always asked for every score (`SimilarityThreshold=0`) and the thresholds are applied in Python, so changing
them needs no AWS change. Tune them on real, consented photos taken the way farmers send them (WhatsApp recompresses images).

### For ezina-connect

`FaceMatchResult` keeps field names compatible with ezina-connect's face check (`verified`, `threshold`, `confidence_band`,
`liveness_passed`, `face_found_id`, `face_found_selfie`, `model`, `processing_ms`, `error`, `warnings`). To plan for: the score
is `similarity` (0-100, higher is better) where the current external API returns `distance`, and `confidence_band` is
`match` / `possible_match` / `no_match`. `NameResult` carries `name` for clients that read `name`.

### Status and known limits

Built and tested against stubbed Rekognition responses only (`ezina_id_verify/tests`, run `pytest ezina_id_verify`); never run
against real AWS, so Rekognition's real OCR line splitting, confidences and face scores are unverified. The label and layout
rules are tested on synthetic layouts (`python ezina_id_verify/tests/make_fixtures.py` regenerates the fixtures; never add a real
person's ID or face): real photos will bring OCR noise, so expect to add label variants and stop words. Only Rekognition OCR
is implemented (`name/ocr.py` is where Amazon Textract would plug in). The Docker targets have not been built here.

## Tests

```bash
cd ezina-connect && pytest
pytest ezina_id_verify      # the ID verification module
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
