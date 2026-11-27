# Progress

Last updated: 2026-11-27

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
| Web | Marketing site www.ezina.ai (`ezina-web/`, pnpm workspace: `apps/web` + `packages/ui` + `packages/config`), static export for Cloudflare Pages | **Built, not deployed** (content placeholders open; see below) |

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

- Marketing site (`ezina-web/`, 2026-11-27): `pnpm build` exports `/`, `/privacy`, `/terms`, `sitemap.xml`,
  `robots.txt`, icons and OG image to `apps/web/out`; lint and typecheck pass; axe (WCAG 2 A/AA) shows no violations
  on the home and privacy pages at 390px and 1280px. All copy and flags are in `ezina-web/apps/web/content/site.ts`.
- Marketing site update (2026-11-27, second pass): official logo (www.ezina.ai/logo.png, margin trimmed only) in
  header, footer, favicon, chat avatar and OG image; new light hero (headline + animated WhatsApp phone + count-up
  stats 1K+ / 10+ / 24/7 / 3+); WhatsApp-style chat mockups (tails, ticks, typing indicator, wallpaper; carousel on
  phones); "Request early access" form removed; every Get Started is a disabled "Coming soon" button while
  `getStartedUrl` is null. lint, typecheck and build pass; axe clean, no horizontal overflow at 375px and 1440px;
  reduced motion shows the final content at once.
- Third pass (2026-11-27): phone mockup removed from the hero (centred text-led hero over a sunrise/fields backdrop
  with the stats card); WhatsApp demo restyled to the owner's reference images (green header, "online", larger
  bubbles, "Type a message" + green mic) on a sky-to-field backdrop. lint, typecheck, build and axe pass at 375/1440.
- Fourth pass (2026-11-27): hero rebuilt as a full-bleed photo hero (cornfield at sunset, Pexels 33443252) in the
  style of eiziba.com: green overlay, white headline, glass pill, Coming-soon Get Started, inline count-up stats, three
  glass feature cards. Reference images moved to `ezina-web/docs/refs/` (not deployed). Build, typecheck, lint and axe
  pass at 375/1440. The WhatsApp section is still to be redone.
- Fifth pass (2026-11-27): WhatsApp demo redesigned as one large tilted phone + 3 auto-advancing, clickable steps,
  floating cards, a blob + dot-grid backdrop and a topographic chat wallpaper (CSS/SVG). Tested at 375/768/1440: autoplay,
  click, arrow keys, hover pause, reduced motion (final state, no autoplay), no horizontal scroll, axe clean, build
  passes. Example figures (P9.50–P11.00/kg) are owner-provided and labelled "example figures".
- Sixth pass (2026-11-27): demo extended to 4 steps (quick-reply buttons with a tap highlight, then the farmer's
  choice and Ezina's confirmation) plus a "Matching buyers" card; the phone tilt was removed. Checked at 375/768/1440:
  full 4-step autoplay loop, clicks, keys, hover pause, reduced motion, no horizontal scroll, axe clean, build passes.
- Seventh pass (2026-11-27): the WhatsApp demo fits one screen. The phone is sized by viewport height (max 560px,
  9:18), the chat scrolls inside the phone (per-step scenes), the step list is compact and the duplicate step-3
  question was removed. At 1440×900, 1366×768, 1280×720, 768×1024 and 375×667 the heading, full phone, first message
  and step controls are all visible with no page scroll; the page never moves during autoplay; axe clean; build
  passes. The floating mobile WhatsApp button hides while the demo is on screen.
- 2026-11-27: "How Ezina works" intro and the first FAQ answer now say "Ezina uses AI and verified evidence…".
  "Who it's for" became "What is Ezina for?" with 4 equal-height cards (farmers with a Free badge, buyers,
  institutions, export partners), wording from the original site, and no Get Started. Checked at 375/768/1280/1440;
  axe clean; build passes.
- 2026-11-27: "What buyers receive" redesigned as a one-screen stepper (card left, steps right; 3 steps: report,
  opportunity, evidence & uncertainty) sharing the new `StepTabs` component with the WhatsApp demo. Progress-bar
  auto-advance, staggered item animations, floating note per step. Tested at 1440×900, 1366×768, 1280×720,
  768×1024 and 375×667: everything fits one screen, auto-advance 1→2→3→1, hover pause, click and keys, reduced motion
  (no auto-advance, final states), no page scroll, axe clean. The WhatsApp demo was re-tested after the refactor and
  still passes. Build passes.
- 2026-11-27: Validation story rebuilt as the third stepper (card on the right) with an owner-provided, labelled
  illustrative scenario (maize, Kenya, example figures) replacing the `[TODO]` placeholders, plus the real
  "Early validation: 24 farmers" line. Stepper logic is shared in `useStepper`. Tested at 1440×900, 1366×768,
  1280×720, 768×1024 and 375×667: one screen, auto-advance 1→2→3→1, hover pause, keys, reduced motion, no page scroll,
  axe clean; the buyers stepper was re-tested after the refactor. Build passes. Removed from the page: the 20/20
  questionnaire findings and "what we're proving next".
- 2026-11-27: added "Why choose Ezina" (5 items, original titles) and rebuilt "How Ezina earns" as pricing-style
  cards without prices (`#pricing`, a "Pricing" nav link), using the original site's wording and an on-scroll
  `Reveal`. Tested at 375/768/1024/1440: Why choose fits one screen, cards are equal height with CTAs aligned, no
  prices or Get Started, axe clean, no horizontal scroll; reduced motion shows everything. Build passes.
- 2026-11-27: new /contact ("Talk to us") page, frontend only: a pill-style form with plain-TS validation, a
  honeypot, no CAPTCHA, and the success, error and sending states. Submission goes through `lib/contact.ts`
  (`NEXT_PUBLIC_CONTACT_MODE` mock|api, `NEXT_PUBLIC_CONTACT_API_URL`); the API contract is in the README. Every
  "Talk to us" now links to /contact; it is in the sitemap. Tested at 375/768/1440:
  - validation (empty, bad email, short message, bad phone), mock success, reset and honeypot (no submit);
  - an api-mode test build against a local endpoint: 200 success, 400 field error with focus, 500 error with input
    kept, exact payload checked;
  - axe clean, build passes (mock mode).

  **Pending (backend):** an endpoint implementing the contract; then set mode=api and the URL, and rebuild.
  **Pending (owner):** confirm the "Where we work" cities.
- 2026-11-27: "What is Ezina for?" Institutions and Export partners links now go to `#pricing` and highlight the
  Institutions or Buyers pricing card (pulse once; a static ring under reduced motion). Tested from the top of the
  page at 1440 and 375: lands just below the header (73px) and the right card rings. Build passes.
- 2026-11-27: header main action is now a primary orange "Talk to us" button (to /contact) instead of Get Started /
  Coming soon, also at the bottom of the mobile menu. Get Started stays elsewhere (hero, closing) and getStartedUrl is
  kept in site.ts. Checked at 375/768/1440: one Talk to us in the bar, menu button works, axe clean. Build passes.
- 2026-11-27: WhatsApp demo phone made about 10% taller (version B, chosen from a temporary A/B/C preview page that has
  since been deleted, along with its screenshots). Max 616px; still one screen at 1440×900, 1366×768, 1280×720,
  768×1024 and 375×667, with internal chat scroll and auto-scroll intact; axe clean; build passes.
- 2026-11-27: WhatsApp phone a further 10% taller (max 678px; tablets have their own cap). Fits one screen at
  1440×900 (678), 1366×768 (600), 1280×720 (552), 1024×768 (600), 768×1024 (638), 390×844 (590) and 375×667 (413).
  Axe clean; build passes.

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

- **Marketing site:** not yet deployed to Cloudflare Pages; there is no lead-capture form (early access removed;
  "Get Started" is "Coming soon" until `getStartedUrl` is set); `[TODO` placeholders remain in `content/site.ts`
  (price examples, validation story, main crops list, founder LinkedIn URLs, legal entity/address/law/retention);
  legal pages are drafts pending legal review. The official logo file is a JPEG named `.png` with an opaque cream
  background; a transparent or SVG version would look cleaner on dark sections. Turbopack fails on Windows+pnpm (lightningcss native module), so `dev`/`build` use `--webpack`.

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
9. Marketing site: fill the `[TODO` placeholders, legal review of /privacy and /terms, set `getStartedUrl` when the
   app is ready, deploy
   `ezina-web` to Cloudflare Pages (root `ezina-web`, output `apps/web/out`), point www.ezina.ai at it and redirect the apex.

## Decisions (with reasons)

- **Marketing site is a separate pnpm workspace in `ezina-web/` (2026-11-27).** Own lockfile, build and deploy; no
  dependency on the Python backend. Static export (`output: "export"`) so it runs on Cloudflare Pages with no server,
  and all content (tables, FAQ, chats) is in the HTML. Brand tokens are from the original ezina.ai stylesheet; button
  orange is darkened to `#d4370c` so white text meets WCAG AA. `ezina.ai` is the only domain (LinkedIn page URL
  `linkedin.com/company/ezina-tech` kept). The original site's illustrative "Agricultural Indices" table, long roadmap
  and "Why choose Ezina" list were dropped. Future `apps/app` (app.ezina.ai) reuses `@ezina/ui`.
- **Marketing site second pass (2026-11-27, owner request).** Official logo used as-is apart from trimming its empty
  margin (owner approved; untrimmed it was unreadable at header size). Hero stats 1K+ farmers, 10+ crops, 24/7, 3+
  countries confirmed by the owner for publishing; validation copy reworded ("pre-product" removed, the 24 farmers
  described as the structured research record) so it doesn't contradict them. Early-access form and `appLive`
  removed; `getStartedUrl: null` renders a disabled "Coming soon" button everywhere.

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
- **ID name check is advisory and never verifies.** *(The external HTTP extraction API described here was replaced by `ezina_id_verify`; see "Rekognition integration" at the end of this section.)* After an ID front is stored, an external extraction API
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
- **Selfie face check is advisory and never verifies.** *(The external HTTP face API described here was replaced by `ezina_id_verify`; see "Rekognition integration" at the end of this section.)* After a selfie is stored, an external face-verification API
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

### Rekognition integration (2026-11-23): the two external HTTP APIs are replaced by the `ezina_id_verify` package

- **What changed.** `doc_extract_service.py` now calls `ezina_id_verify.extract_name(doc_type, id_bytes)` and `face_verify_service.py` calls
  `ezina_id_verify.match_face(id_bytes, selfie_bytes)` in-process (AWS Rekognition; the package lives in `ezina_id_verify/` at the repo root and is
  installed with `pip install -e .`, which `requirements.txt` now does with `-e .`). The two classes keep their names, `available`, `aclose` and (for
  the face service) `verify(...)`; `DocExtractService.extract_name` now takes `id_document_type=` and `data=` and returns a `NameExtraction` (status, name,
  method, confidence, reason) instead of a bare string, because a string cannot say SKIPPED / unsupported file / ERROR. Every package exception is
  caught in the services: `UnsupportedDocType` -> SKIPPED, `UnsupportedFile` -> ask for a JPEG/PNG photo (an attempt), `RekognitionServiceError` (or any
  other failure) -> ERROR (the farmer is never blocked). Nothing is retried around the calls (the package retries AWS errors).
- **Config.** `id_documents.yaml` `extraction:` now maps an ID type to `verify_doc_type` (PASSPORT passport, AADHAAR_MASKED aadhaar, PAN pan, VOTER_ID
  voter_id, DRIVING_LICENCE driving_licence, OMANG botswana_omang); KCC has none, so its name check is SKIPPED without a call. Removed settings:
  `DOC_EXTRACT_API_URL/_KEY/_KEY_HEADER/_TIMEOUT_SECONDS/_MAX_RETRIES/_RETRY_BASE_DELAY`, `FACE_VERIFY_API_URL/_KEY/_KEY_HEADER/_TIMEOUT_SECONDS/
  _MAX_RETRIES/_RETRY_BASE_DELAY` and `FACE_VERIFY_SHARPEN_RETRY` (the Rekognition path has no quality gate to work around); an old `.env` that still sets
  them is simply ignored. The on/off switches, attempt limits and name thresholds stay. AWS credentials come from the standard AWS chain (not from `.env`);
  the package's own settings (`AWS_REGION`, `FACE_MATCH_THRESHOLD`, ...) are in `.env.example`.
- **Face result mapping** (`classify`): error -> ERROR, no face in the ID -> NO_FACE_ID, no face in the selfie -> NO_FACE_SELFIE, verified -> MATCHED, else
  MISMATCH (so `possible_match` is a MISMATCH). `liveness_passed` is always None from Rekognition and is never read, so LIVENESS_FAILED is never set (the enum
  value stays for existing rows; the finger challenge is still the liveness check). **This changes the earlier rule** "an explicit no-face flag wins over `error`":
  a package result that carries both (a photo Rekognition rejected outright, `error="selfie_image_rejected"`) is now ERROR, as specified. Quality warnings
  (`eyes_closed`, `selfie_blurry`, `selfie_dark`, `sunglasses`, `multiple_faces_selfie`) never override MATCHED; for MISMATCH and NO_FACE_SELFIE one specific tip is
  added to the retry message (`messages.face_tip`).
- **Database (migration `0006`, inspector-guarded, tested on SQLite both ways).** New nullable columns on `identity_documents`: `name_extract_method`,
  `name_extract_confidence`, `face_similarity` (0-100), `face_selfie_quality_ok`; the check constraint `ck_identity_documents_face_only_selfie` is extended so the
  last two can only be set on SELFIE rows. `face_distance` and `face_detector` stay (nullable, no longer written). The admin farmer-detail endpoint returns
  `face_similarity`, threshold, band, `face_selfie_quality_ok`, warnings and the name method/confidence instead of the distance. **Run `alembic upgrade head`.**
- **JPEG and PNG only for identity images.** `IDENTITY_ALLOWED_MIME` / `IDENTITY_DOCUMENT_MIME` no longer include WebP or PDF. A PDF (or any non-JPEG/PNG) at
  `COLLECT_ID_DOCUMENT`, as a photo or as a document message, is refused with "Please send a photo of your ID: tap 📎 (Attach) -> Camera or Gallery." and counts
  as an attempt. An ID front stored as a PDF before this change is still converted to a PNG for the face check.
- **Files touched outside `ezina-connect/`** (they had to change): `requirements.txt` (`-e .`), the root `Dockerfile` (the ezina-connect image installs the
  package non-editable), `.env.example`, `docs/ezina-spec.md`. Files touched in `ezina-connect/` beyond the two services: `workflows/identity_flow.py` (the YAML loader
  now reads `verify_doc_type`), `services/identity_service.py` (the caller: new result, new columns, the PDF message), `services/conversation_service.py` and
  `workflows/messages.py` (the "send a photo" message and the retry tip), `api/admin.py`, `models/identity_document.py`, `config.py`.
- **Known limit (observed on real photos): old, grainy, black-and-white ID photos do not match.** A Voter ID card's printed photo scored about 10 against a clear
  selfie of the same person (the passport, PAN and driving licence of that person scored 95-99; Aadhaar 75). Such an ID ends as MISMATCH and then NEEDS_HELP for
  the operations team, who see the similarity in the admin detail. No threshold change is recommended: a score of 10 is the level of an unrelated face.
- **Not verified:** the whole integration is tested with the package mocked; no real run through WhatsApp -> AWS yet. The Docker image build is untested.
- **Passport label fix (2026-11-23).** A real Indian passport photo returned NOT_FOUND: the MRZ line 1 was cut (no closing `<<`, correctly refused) and the label reader failed twice: a number from the next column (passport no.) sat between "Surname" and its value, and the label read as `film - / Given Name(s)` (noise before the `/`). `name/labels.py` now matches a bilingual label by its part after `/` and skips a digit-only line while looking for the value below a label. Regression test added in `ezina_id_verify/tests/test_name_extract.py` (package suite: 218).
- **Passport: the MRZ is the primary source, also for a lone cut line (2026-11-23).** A first MRZ line whose name field is not closed by `<<` (cut by the image edge or the OCR) is no longer ignored: `mrz.py` returns it flagged `mrz_incomplete` + `mrz_name_unclosed`, and `name_extract.py` accepts it (method `mrz`, warning `mrz_confirmed_by_label`) only when the printed Surname / Given Name(s) start the same way, returning the complete printed spelling; a contradicting or missing printed name means no result (a truncated name is never returned). Package tests: 221.
- **An ID whose name could not be read is deleted, so the farmer can re-send it (2026-11-23).** A farmer who sent the same photo again after a NOT_FOUND got "That photo has already been used" (the SHA-256 is unique and the rejected row kept it). Now, when the name check is NOT_FOUND or the file was not a usable JPEG/PNG, `IdentityService.discard` deletes the stored image and the `identity_documents` row (no unusable personal data is kept; the attempt count lives in the draft, so `IDENTITY_MAX_ATTEMPTS` still applies) and the hash is free again. This replaces the earlier "REJECTED row is kept" behaviour for name-not-found; a NO_FACE_SELFIE selfie is still kept as REJECTED. Photos already used by an ACCEPTED/SUPERSEDED row or by another farmer are still refused. Tests in `tests/test_name_check.py`.
- **Leftover REJECTED rows no longer block a re-send (2026-11-23).** After the delete-on-NOT_FOUND change a farmer still got "That photo has already been used": rows rejected *before* it (status REJECTED, name NOT_FOUND) still held their hash in the database. `IdentityService.ingest` now also discards the farmer's own REJECTED ID row of the same photo and kind, so old data needs no manual cleanup. A selfie, another farmer's photo and the farmer's ACCEPTED/SUPERSEDED photos are still refused. The earlier "same photo" test used the helper's random images and never reused bytes; the tests now pass fixed bytes (`make_image()`), and the leftover test was checked to fail with the fix disabled.
- **A match is never announced to the farmer (2026-11-23, decision).** Name MATCHED and selfie MATCHED only get the plain receipt ("Thank you, your ID/selfie has been received ✅."); the farmer is told only when something does not match or needs redoing (name PARTIAL/MISMATCH, selfie MISMATCH / no face). No "our team will review" line either. A tried "name matches" line was removed again. Test in `tests/test_name_check.py`.
- **A farmer's own replaced ID photo can be used again (2026-11-23).** Duplicate detection (SHA-256) now ignores the farmer's own earlier ID_FRONT photo when it is REJECTED (deleted, as above) or SUPERSEDED (it gives up its hash and keeps its audit data), e.g. after [Upload another ID]. Still refused as "already been used": another farmer's photo, any selfie reuse, and the farmer's current ACCEPTED ID. Tests in `tests/test_name_check.py` (`_old_id_row` helper).
- **Duplicate-photo message diagnostics (2026-11-23).** A farmer uploading a *different* ID still got "That photo has already been used". `IdentityService.ingest` now logs why (`identity image refused: photo already used` with kind, same farmer and the earlier row's kind/status; no personal data) and an integrity error on insert is no longer reported as a reused photo unless the hash really exists (otherwise "couldn't save that photo", logged as `identity image not saved: integrity error` with the database's constraint text). Root cause not yet confirmed: waiting for the log line from the failing upload.
- **A new ID deletes the old one; a retaken selfie can reuse its photo (2026-11-23).** `IdentityService.supersede` now deletes all of the farmer's ID_FRONT / ID_BACK rows and stored images when a new ID is uploaded or a replacement is asked for (before: kept as SUPERSEDED). Selfies keep their rows (the face-check attempt total is read from them) and image, but a SUPERSEDED / REJECTED selfie gives up its hash (`release_hash`), so sending the same selfie again after a mismatch or "no face" is not blocked as "already used" (it will get the same result and count as an attempt). Another farmer's photo and the farmer's current ACCEPTED photo are still refused. Trade-off: deleted IDs no longer take part in cross-farmer duplicate detection. Tests updated/added in `test_identity.py`, `test_name_check.py`, `test_face_check.py`.
- **The ID check now shows the same "checking" message as the selfie (2026-11-23).** Before the name check runs the farmer gets "Thank you! Checking your ID, this takes a few seconds…" immediately (not only after 5 s), then the receipt or the name message. Not sent when no check runs (switched off or an ID type with no `verify_doc_type`). `DOC_EXTRACT_HOLD_SECONDS` is removed (setting, `.env.example`, spec). Tests in `tests/test_name_check.py`.
