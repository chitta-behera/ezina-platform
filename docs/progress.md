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
- **Failed images are not stored** (Python rejections leave nothing behind), so a retaken photo is never confused with a
  reused one. The one exception: an ID whose name could not be read (name check NOT_FOUND) is kept as `REJECTED`.
- **A selfie that arrives after its challenge expired is not counted as a failed attempt**; it just gets a new challenge.
- **`anonymize_farmer` refuses to run without the identity service** when the farmer has identity images, so images
  can never be left behind by a forgotten argument.
- **Environment variables beat `.env`** (pydantic-settings default). A stray system `ANTHROPIC_BASE_URL` /
  `ANTHROPIC_API_KEY` caused connection-refused errors during live testing.
- **Review edits are text-only.** At `REVIEW_REGISTRATION` an image is refused (no farm photo is added, no ID or selfie is stored). A country correction that would invalidate the chosen ID type is refused, because it would silently wipe the ID. Text details (name, country, farm name, address, crops, land, language) stay editable. Covered by 2 tests in `tests/test_identity.py` (195 tests pass).
- **"No" / "not now" to the welcome question ends the prompt.** An unregistered farmer with no active flow who declines (intent DENY, or the plain words no / not now / no thanks) now gets the "No problem! Message us whenever you are ready" reply (`Action.DECLINE`). Before, DENY fell through to the general handler, which re-sent "Would you like to register your farm?" every time. Covered by 3 parametrised tests in `tests/test_registration_flow.py`.
- **ID name check is advisory and never verifies.** After an ID front is stored, an external extraction API
  (`doc_extract_service.py`) returns the name on it; `name_match.py` (rapidfuzz, tolerant of order, initials, titles,
  accents, typos) compares it with the farmer's name: MATCHED / PARTIAL / MISMATCH / NOT_FOUND / ERROR / SKIPPED. Which ID
  types are sent and which fields hold the name is config (`extraction:` in `id_documents.yaml`, validated at startup).
  Only PASSPORT, PAN and VOTER_ID are configured; the rest are SKIPPED. Mismatch: two buttons ([Change my name] re-compares
  without a new API call, [Upload another ID] supersedes and re-checks); free text is read by Claude; after
  `NAME_CHECK_MAX_ATTEMPTS` the ID becomes NEEDS_HELP for the operations team and the flow continues. API failure (ERROR)
  never blocks the farmer. `extracted_name` is stored only on the identity row (migration `0004`) and returned only by the
  admin farmer-detail endpoint; it is never logged, never in the draft, never in a Claude prompt. Off by default
  (`DOC_EXTRACT_ENABLED=false`). Tests: `tests/test_name_check.py` (88).
  The live API wraps fields as `{"fields": {"name": {"value": ...}}}`, so `name_fields` are `fields.name.value` etc.; the
  first live run read nothing (NOT_FOUND) because the config expected a flat `name`. Only VOTER_ID was confirmed against a real
  response; PASSPORT and PAN paths are assumed to follow the same envelope.
- **The "Checking your ID..." holding message is sent directly, not through the outbox**, because the outbox only flushes
  after the turn's commit. It carries no state; the real reply still goes through the outbox.
- **Not done:** the background re-run of ERROR checks ("may re-run later"); a real run against the live extraction API
  (only mocked so far); PAN and Voter ID are covered by unit tests only (the end-to-end tests use a Botswana passport).
- **Run `alembic upgrade head`** for migration `0004` before deploying (Postgres too).
- **Selfie face check is advisory and never verifies.** After a selfie is stored, an external face-verification API
  (`face_verify_service.py`) compares it with the accepted ID front (a PDF ID is rendered to a PNG with pypdfium2 first).
  Python reads the result in a fixed order (error, no face in the ID, no face in the selfie, liveness, verified):
  MATCHED / MISMATCH / NO_FACE_ID / NO_FACE_SELFIE / LIVENESS_FAILED / ERROR, plus SKIPPED (off, or PDF could not be
  converted) and PENDING_ID (no accepted ID yet; it runs automatically when one is accepted, including from the later
  identity flow, and again when a new ID replaces the old one). Mismatch: [Take a new selfie] / [Upload another ID]
  (free text is read by Claude through the new `identity_choice` field); the farmer never sees a score. After
  `FACE_VERIFY_MAX_ATTEMPTS` failed checks `selfie_status` becomes NEEDS_HELP for the operations team and the flow
  continues. The attempt total is a running count on the SELFIE rows. Results live on the selfie's `identity_documents`
  row (migration `0005`, no new tables; a check constraint keeps `face_*` to SELFIE rows) and are returned by the admin
  farmer-detail endpoint. Off by default (`FACE_VERIFY_ENABLED=false`). Tests: `tests/test_face_check.py` (62).
- **The reply guard now allows "the selfie does not match" only for the Python-supplied face result**
  (`face_result_supplied`); in every other reply it is still blocked, and calling an ID fake is always blocked.
- **Not done (face check):** the background re-run of ERROR checks ("may re-run later"); a real run against the live face
  API (only mocked so far, so its response shape and the ~15 s latency are untested end to end).
- **Run `alembic upgrade head`** for migration `0005` before deploying (Postgres too; tested on SQLite only), and
  `pip install -r requirements.txt` for `pypdfium2`.
- **The face API answers "no face found" with HTTP 422 and a normal result body** (found with a synthetic probe after the
  first live run logged `status=422`). The client now reads a 4xx whose body is a result as a result, and an explicit
  `face_found_*: false` wins over the `error` text, so NO_FACE_ID / NO_FACE_SELFIE can happen. This refines the written
  order (error first), which would otherwise have turned every no-face answer into a silent ERROR. A real validation 4xx
  (`detail`) now fails with the field names in the logged reason. Tests: `tests/test_face_check.py` (68).
- **The face API has its own image-quality gate, and WhatsApp-compressed photos fail it.** Replaying the stored ID and selfie of a live test returned `422 {"error": "image quality check failed", "issues": ["ID photo is too blurry (sharpness 18.5 < 25.0)", "selfie is too blurry (sharpness 18.4 < 60.0)"]}` (the same photos pass in Postman as originals). The client now keeps the `issues` text in `face_error_message` for operations; the result stays ERROR, so the farmer is not blocked and is told nothing. The fix for a real run belongs on the API side (its sharpness thresholds, or a way to skip the gate for WhatsApp images). Tests: `tests/test_face_check.py` (70).
- **Face check ERROR now tells the farmer it is pending** (a live run returned `http_401` and the farmer saw only "selfie received"): "We couldn't finish the automatic photo check right now. Your selfie is saved, and the Ezina team will complete the check." No reason or code is shown. SKIPPED and PENDING_ID still say nothing. A live 401 means the API key is not being sent (`FACE_VERIFY_API_KEY` / `FACE_VERIFY_API_KEY_HEADER`).
- **Face check: sharpen-and-retry for "too blurry" rejections (`FACE_VERIFY_SHARPEN_RETRY`, default true).** The face API's own quality gate rejected every WhatsApp photo ("selfie is too blurry (sharpness 15 < 60)"), so the automatic check never ran. An experiment on a stored live pair: unsharp mask r=2 / 250% passed the gate and matched; r=3 / 400% failed the API's liveness check; a 2x upscale still failed. The client now retries ONCE with a mildly sharpened JPEG copy of only the photo(s) the API names as blurry; stored images are unchanged; a second failure is ERROR (farmer told it is pending). Validated on ONE real pair only: watch the MATCHED / LIVENESS_FAILED / MISMATCH mix on real farmers. The proper fix is still to relax the sharpness thresholds on the API side (then set FACE_VERIFY_SHARPEN_RETRY=false). Tests: `tests/test_face_check.py` (76).
- **ID and selfie upload instructions now use the farm-photo style (wording only).** The ID prompt says "...of the *front* of your <ID>: tap 📎 (Attach) → Camera or Gallery." The selfie prompt says "please send a *new selfie*: tap 📎 (Attach) → Camera and take it now with your front camera..." (Camera only, no Gallery, because a selfie must be a live photo and a file or gallery image is refused). No logic changed; no existing test asserted the old wording. Added `test_id_and_selfie_prompts_use_the_attach_wording_of_the_farm_photo_step`. Spec sample conversation updated. The retry messages (FACE_NEW_SELFIE, FACE_ID_UNCLEAR, NAME_NOT_FOUND) keep their own wording.
- **Masked Aadhaar is now name-checked.** A live test showed `name_check_status = SKIPPED` for an `AADHAAR_MASKED` upload because the `extraction:` section of `id_documents.yaml` only listed PASSPORT, PAN and VOTER_ID (so the check silently did not run, by configuration, not a fault). Added `AADHAAR_MASKED: doc_type "aadhaar", name_fields ["fields.name.value"]`, confirmed against the live extraction API (it returns `fields.name.value` for `aadhaar`). Still without a name check: DRIVING_LICENCE, OMANG, KCC (no `doc_type` configured; the API also lists `za_id` for South Africa, not wired). Tests: `tests/test_name_check.py`.
