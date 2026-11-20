# Progress

Last updated: 2026-11-19

## Phases

| Phase | Scope | Status |
|---|---|---|
| 1 (MVP) | Webhook + signatures + dedupe + durable ordered processing; WhatsApp text/buttons/lists; Claude service with structured output; registration state machine through submission; location + photo handling; models + migration; core tests | **Done** |
| 2 | Admin endpoints, verification notifications, human handoff + release, status checks | **Done** |
| 1 (spec update) | Identity verification: ID document + live selfie (`COLLECT_ID_DOCUMENT`, `COLLECT_SELFIE`), private identity storage, `identity_documents`, submission rule | **Done** (Python checks only; see below) |
| 2 | Identity phase 2: admin signed URLs + `identity_access_log`, Claude vision quality check, reminders, retention job, VERIFIED gate | **Pending** |
| 2 | `ADD_FARM`, `ADD_CROP`, `UPDATE_CROP`, `UPDATE_PROFILE` flows | **Pending** (currently a polite "coming soon"; `workflows/farm_flow.py` is ready to reuse) |
| 3 | Harvest availability flow (`workflows/harvest_flow.py`), opportunity notifications | **Pending** (`harvests` table and extraction fields exist) |
| 3 | Prompt-evaluation script (~30 messages, real Claude API, on demand) | **Pending** |

## What is working

- Verified on a real setup (Meta test number + ngrok): webhook verification, inbound messages reaching the app,
  replies from Claude flowing back to the phone.
- 193 automated tests pass (SQLite + mocked Meta/Anthropic), covering all 20 areas in the spec's original testing
  list, the five workflow variations (multi-answer, review correction, resume next day, typed address, cancel) and the
  identity-verification behaviour (`tests/test_identity.py`) and the farm-address behaviour (`tests/test_address.py`).
- Registration flow end to end: Hi -> consent -> language (skipped when clearly detected) -> name -> country ->
  full address -> crops -> area -> location (optional) -> ID document -> selfie -> farm photo (optional) ->
  crop photo (optional) -> summary -> confirm -> `SUBMITTED`; `PENDING` + `verifications` row **only when both the ID
  document and the selfie were received**, otherwise `NOT_SUBMITTED`.
- Identity verification: ID types per country from `app/config/id_documents.yaml` (India, Botswana) shown as a list
  plus "I don't have any of these" (-> `NEEDS_HELP`) and "Send later" (-> `DEFERRED`); front photo only (the back side is not requested; `back:` flags in the YAML are all false); Aadhaar
  masking reminder; ID accepted as an image or as a WhatsApp document (image/PDF, only at `COLLECT_ID_DOCUMENT`);
  random 1-5 finger selfie challenge with `SELFIE_CHALLENGE_TTL_MINUTES` expiry and a new challenge on every retry;
  `IDENTITY_MAX_ATTEMPTS` failures -> `NEEDS_HELP` and the flow continues. Python checks only: MIME, size, minimum
  resolution (`IDENTITY_MIN_IMAGE_PX`), SHA-256 never seen before (unique index, across all farmers).
- Identity images go to a separate private store (`S3_IDENTITY_BUCKET` with server-side encryption, or
  `<MEDIA_LOCAL_DIR>_identity` locally), are never public, never captioned, never sent to Claude. Typed ID numbers
  (8+ digits, or a PAN pattern) are redacted at ingest, before the messages table, draft, logs or prompt.
- Later upload (`SUBMIT_IDENTITY_DOCUMENTS`, or the "Send now" button after submission) collects only what is missing and
  sets `PENDING` + a `verifications` row once both are received.
- Farm address: one question ("What is the full address of your farm?") with an instruction and an example for the
  farmer's country from `app/config/address_formats.yaml` (IN, BW, KE, default); stored as ONE text
  (`farms.full_address_text`, migration `0003`; `village`, `district`, `address` were dropped). Claude reports
  `address_missing_parts` (advisory, never stored); Python keeps only the country's expected parts, asks only for those
  (max 2 follow-ups, then accepts the address as given), and joins the answers into one text. A landmark is valid;
  minimum 10 characters. A correction at review (Claude returns the whole corrected address) replaces
  `full_address_text` only after the farmer answers Yes. `farm_flow.next_farm_stage` carries the same rule for ADD_FARM.
- Admin API (list/view farmers, verify with WhatsApp notification, release handoff), `/api/whatsapp/send`,
  anonymisation helper, startup recovery of unprocessed messages, outbox delivery with retry/backoff and 24h-window
  template fallback.

## Known issues / not verified

- **Not yet verified live:** PostgreSQL (Neon/Supabase) behaviour incl. `pg_advisory_xact_lock` and PgBouncer; the S3
  storage backend; template messages outside the 24h window (test number only offers `hello_world`); the full
  registration run on real WhatsApp (in progress by the product owner).
- The configured model (`claude-sonnet-5-5`) rejects a forced `tool_choice`; the service falls back to `auto` and logs
  one warning per process start. Cosmetic; could skip the forced attempt for this model.
- Templated messages (consent, summary, fallbacks, buttons) are English-only.
- Rate limiting is in-process (not shared across replicas).
- The Claude call runs inside the farmer's DB transaction (holds the per-farmer lock and a pooled connection).
- Initial Alembic revision is `create_all` from the models; later revisions must be autogenerated against PostgreSQL.
- WhatsApp temporary access token expires about every 24h (symptom: `token rejected` CRITICAL log).

- **Identity phase 2 is not built, so ops cannot yet look at the images:** no signed-URL endpoint or
  `identity_access_log`; the admin farmer view lists identity metadata and statuses only (no storage keys). `VERIFIED`
  is not yet blocked when an accepted ID/selfie is missing. No reminders (`IDENTITY_REMINDER_HOURS`), no retention job
  (`IDENTITY_MEDIA_RETENTION_DAYS`); only cancellation and `anonymize_farmer(..., identity=...)` delete images.
- **Python cannot see the picture:** whether the selfie shows the requested number of fingers, whether the photo is
  blurry/cropped/a screenshot, and whether an ID is the right type are NOT checked until the Claude vision
  `ImageQualityService` (phase 2) exists. Today only expiry, MIME, size, resolution and image reuse are enforced; the
  challenge number is stored on the selfie row so ops can compare. A wrong kind of image (e.g. a selfie sent as the ID)
  is saved as sent. Known limitation (spec): WhatsApp strips metadata and cannot force camera capture.
- `LivenessProvider` (`LIVENESS_PROVIDER`), `IMAGE_QUALITY_CHECK_ENABLED`, `IDENTITY_URL_TTL_SECONDS` are not implemented
  and are deliberately absent from `.env.example`. ID type names exist in English only (YAML supports per-language names).
- Alembic `0002` is written by hand and guarded (checks before adding) because `0001` runs `create_all` from the
  current models; tested on SQLite (fresh DB, pre-feature DB, downgrade) but **not yet run against PostgreSQL**.
- The ID-number redactor is a heuristic (8+ digits, PAN pattern): short alphanumeric passport numbers are not caught.

## Pending tasks

1. Finish live testing of the full registration flow on WhatsApp and fix anything found.
2. Verify against Neon/Supabase PostgreSQL (run `alembic upgrade head`, process messages, check advisory locks).
3. `ADD_FARM` / `ADD_CROP` / `UPDATE_CROP` / `UPDATE_PROFILE` flows (reuse `farm_flow.py`).
4. Harvest availability flow + opportunity notifications + template messages.
5. Prompt-evaluation script.
6. Translate templated messages for launch languages (at least the consent text).
7. Production: System User token, real business number, own approved templates, S3 buckets (farm media and the
   separate encrypted identity bucket).
8. Identity phase 2 (see Known issues): signed URLs + access log, vision quality check, reminders, retention, VERIFIED
   gate. Confirm retention periods with legal before production.

## Decisions (with reasons)

- **Farm address is one text, parts are never stored.** Follow-up questions are templated (English) so the wording and
  the example are exactly what Python picked for the country; Claude's own wording for the address question is used only
  if it contains that example verbatim. Claude's `address_missing_parts` is advisory: Python filters it to the country's
  expected parts and owns the follow-up count. The "default" example in `address_formats.yaml` was written by us (the
  brief gave none); the instruction texts are English only. Migration `0003` has been tested on SQLite only (fresh,
  pre-change with data, downgrade), not on PostgreSQL.

- **No LangChain/LangGraph.** The spec lists them in the stack but also says no unnecessary agent frameworks; a small
  deterministic state machine + one SDK call is simpler and easier to test. The project owner confirmed this rule.
- **Claude gets exactly one tool and no write access.** Structured output via tool use; Python validates and decides.
- **Stage is derived from the draft** (`resolve_stage`) instead of hand-written transitions, so corrections, multi-
  answer messages and resume-after-pause need no special cases.
- **Draft in `conversations.draft`, farm rows created on confirmation.** Guarantees nothing personal is stored before
  consent and lets a cancel discard everything cleanly.
- **Outbox for replies** (queued rows committed with the state change, sent after commit): no lost or duplicated
  replies across crashes. Outbound timestamps are strictly increasing so replies are never reordered.
- **Per-farmer ordering** via in-process lock + `pg_advisory_xact_lock` (xact variant works behind PgBouncer
  transaction pooling used by Neon/Supabase pooled URLs).
- **Stale (out-of-order) messages are persisted but not applied**, using WhatsApp timestamps.
- **No fuzzy country matching.** A typo must never silently become another country; low confidence triggers a
  yes/no confirmation instead.
- **Claude calls use SDK retries** (exponential backoff on 429/5xx/overloaded); invalid output retried once, then a
  templated fallback.
- **Admin surface fails closed:** `/api/admin/*` and `/api/whatsapp/send` return 503 while `ADMIN_API_KEY` is empty.
- **Optional steps share one pattern** (📎 instruction + single "Skip for now" button). The crop-photo "Send photo"
  button from the spec example was removed because it only prompted the same action as the attach button.
- **ID/selfie prompts are templated, not worded by Claude:** the ID list is interactive and the liveness challenge
  must be exact, so both stages are in `TEMPLATE_ONLY`. Claude still interprets free text there and only ever sees the
  status words RECEIVED / DEFERRED / NEEDS_HELP / NOT_PROVIDED.
- **Identity is part of the registration stage order only** (`next_farm_stage(..., with_identity=True)`), so the
  reusable farm sub-flow for ADD_FARM does not ask for it again.
- **Failed images are not stored** (no `REJECTED` rows yet): Python rejections leave nothing behind, so a retaken photo
  is never confused with a reused one. `REJECTED` is reserved for the vision check.
- **A selfie that arrives after its challenge expired is not counted as a failed attempt**; it just gets a new challenge.
- **`anonymize_farmer` refuses to run without the identity service** when the farmer has identity images, so images
  can never be left behind by a forgotten argument.
- **Environment variables beat `.env`** (pydantic-settings default). A stray system `ANTHROPIC_BASE_URL` /
  `ANTHROPIC_API_KEY` caused connection-refused errors during live testing.
- **Review edits are text-only.** At `REVIEW_REGISTRATION` an image is refused (no farm photo is added, no ID or selfie is stored). A country correction that would invalidate the chosen ID type is refused, because it would silently wipe the ID. Text details (name, country, farm name, address, crops, land, language) stay editable. Covered by 2 tests in `tests/test_identity.py` (195 tests pass).
- **"No" / "not now" to the welcome question ends the prompt.** An unregistered farmer with no active flow who declines (intent DENY, or the plain words no / not now / no thanks) now gets the "No problem! Message us whenever you are ready" reply (`Action.DECLINE`). Before, DENY fell through to the general handler, which re-sent "Would you like to register your farm?" every time. Covered by 3 parametrised tests in `tests/test_registration_flow.py`.
