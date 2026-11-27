# Ezina marketing website: spec

Source of truth for www.ezina.ai (`ezina-web/`). This is the product owner's brief (2026-11-27), followed by the
decisions made while building it. **Read this before changing the site.** Status and open work: `../../docs/progress.md`.

---

## 1. The brief

### Positioning
Marketing website for Ezina at https://www.ezina.ai, positioned as **"AI-Powered Agri Trade"**.

### What Ezina is
**Ezina is NOT a marketplace.** It does not sell products, move money, or take a cut of sales. It is trust and
intelligence infrastructure for agricultural trade: it verifies buyers and suppliers, provides market price
intelligence, and connects farmers with real, verified opportunities. Never use marketplace wording such as "shop",
"cart", "buy now" or "listings for sale".

### Audience
Primary audience: buyers, processors, export partners, institutions and investors. Farmers use Ezina almost entirely
through WhatsApp, not the website. Write for business decision-makers: what verified supply and market intelligence
they get, how verification works, and why they can trust it. Show farmers as the source of verified supply and as
proof that the product works, but not as the main readers.

### Source content and tone
- The original site (www.ezina.ai, pre-rebuild) is the source of truth for copy, facts, founder details, images and tone.
- Keep the honest tone: always say what is verified, what is uncertain, and that verification does not guarantee a
  sale, price or payment.
- **Do not invent facts, customers, numbers, quotes or results.** Where content is missing, use clearly marked
  placeholders `[TODO: ...]` and list them for the owner.
- Core principle: **SHOW the product experience; don't describe the vision.** Prefer real examples, WhatsApp
  conversations, sample verification reports and step visuals over abstract claims and long roadmaps.

### Domain: ezina.ai only
- ezina.tech is no longer used. The only official domain is https://www.ezina.ai.
- Use https://www.ezina.ai in every URL: canonical, og:url, og:image, twitter:image, sitemap.xml, robots.txt
  (Sitemap line), JSON-LD.
- Email: hello@ezina.ai.
- Keep the LinkedIn URL as is (linkedin.com/company/ezina-tech): it is a LinkedIn page address.
- After changes, search the project for "ezina.tech": the LinkedIn URL must be the only match.

### Tech and structure
- pnpm monorepo: `apps/web` (this site), `packages/ui` (shared brand components: colours, fonts, buttons, logo),
  `packages/config` (shared Tailwind, TypeScript, ESLint config). Leave room for a future `apps/app` (buyer/partner
  dashboard at app.ezina.ai, reusing `packages/ui`). Do not build it now.
- `apps/web`: Next.js (App Router) + TypeScript + Tailwind CSS, static export (`output: "export"`) for Cloudflare Pages.
- All content, including tables, must be in the static HTML, not loaded only by client-side JavaScript.
- Mobile-first and lightweight: many buyers and partners in Botswana, Zambia and Kenya browse on phones over slow
  connections. Optimise images, keep JavaScript minimal.
- All copy, stats, FAQs, links and flags in one content file: `apps/web/content/site.ts`.
- Accessible: semantic HTML, alt text on every image (including the logo), good contrast, keyboard-friendly.
- Separately deployable: own package.json, lockfile, build, env variables and deployment; no dependency on the
  backend or any other module in the repo.

### Links and flags (in the content file)
- `whatsappUrl`: https://wa.me/26774257916?text=Hi%20Ezina (wa.me needs the number without "+")
- `appUrl`: https://app.ezina.ai, `signupPath` /signup, `loginPath` /login
- *(Superseded 2026-11-27: early access removed, see decisions.)* `appLive: false`: every "Get Started" goes to the "Request early access" section on the home page (name,
  organisation, role, country, email) and "Log in" is hidden. When `true`, they link to the app. Form: mailto fallback
  or placeholder endpoint `[TODO: form backend]`.
- `email`: hello@ezina.ai

### Global elements
- Header: logo, nav (For Buyers, For Partners, How it works, FAQ, About), a small "Farmers: WhatsApp" link, "Log in"
  (only when appLive), "Get Started" button.
- Small floating WhatsApp button on mobile (must not dominate the page).
- Footer: tagline "Trust that can be verified.", nav links, hello@ezina.ai, LinkedIn, X (@Ezina_AI),
  "Validation footprint: Botswana · South Africa · Zambia", Privacy Policy and Terms of Service links, and the
  disclaimer (in validation, not yet incorporated, no guaranteed sale, price or payment).

### Home page sections (in this order)
1. **Hero**: eyebrow "AI-Powered Agri Trade"; headline "The trust and intelligence infrastructure for agricultural
   trade."; one-line subtext for buyers (verified farmer supply, market intelligence, trusted connections); primary
   CTA "Get Started"; secondary link "Are you a farmer? Chat with Ezina on WhatsApp →"; phone mockup of an Ezina
   WhatsApp conversation; highlights strip of 4 stats from the content file (farmers in the network, crops covered,
   countries (3 in validation), verification checks performed). Show only confirmed numbers.
2. **Who it's for**: two cards, Buyers & Processors and Institutions & Export Partners, 3 benefits each and a
   "Get Started" CTA; below, a strip "Farmers join free on WhatsApp" with the WhatsApp link.
3. **How Ezina works**: 4 steps with icons: Share your needs → We verify → Get matched → Track progress.
4. **How farmers use Ezina (WhatsApp demo)**: presented to buyers as proof that supply and data come from real farmer
   conversations. 3 HTML/CSS chat mockups (not images), labelled "Example conversation":
   (1) farmer asks the tomato price → Ezina asks for location, grade, quantity; (2) Ezina gives price references,
   explains the source, notes what is uncertain; (3) Ezina offers to find a verified buyer or lets the farmer share
   supply; the farmer chooses. WhatsApp-like styling (bubbles, ticks, timestamps) with Ezina branding, not the WhatsApp logo.
5. **What buyers receive**: the original example verification report (ABC Fresh Produce Ltd) and example opportunity
   (Fresh Tomatoes, 2,000 kg, Kweneng), keeping "Example only" / "Not a live offer" labels and the
   checked / confirmed / uncertain breakdown.
6. **Validation story "From a Farmer's Need to a Verified Opportunity"**: The Challenge, What Ezina Did (verified the
   buyer, checked the requirements, matched available supply), The Outcome (including challenges and uncertainties).
   Specifics are `[TODO: real details]`; never invent results. Below: 24 farmers (4 in-depth interviews in Botswana and
   South Africa, 20 questionnaires in Sinda, Zambia).
7. **How Ezina earns**: buyers pay for intelligence subscriptions, verification reports and sourcing services;
   institutions pay for annual contracts and market research; essential access is free for farmers. "Ezina does not
   move money or take a cut of farmer sales." Pricing: "Being validated: talk to us."
8. **FAQ**: native `<details>/<summary>` accordion plus FAQPage JSON-LD: how verification works; what a buyer
   subscription includes; countries and crops; how farmer data is protected (access, consent); is it free for farmers.
9. **Founders**: Alakanani Itireleng (Founder), Chitta Ranjan Behera (Co-founder, Engineering), Frank Deya
   (Co-founder, Growth): photo, role, 3–4 line bio (agriculture, trade, tech, growth), LinkedIn link.
10. **Closing CTA** *(early-access form removed 2026-11-27)*: "Let's grow a more connected agricultural future." with the early-access
    form (appLive false) or "Get Started" (true), a "Talk to us" email link and the farmer WhatsApp link.

Drop or shrink: the long product roadmap (at most "Ezina Market and Ezina Trust first, more to come") and the generic
"Why choose Ezina" list (merged into other sections).

### Legal pages
`/privacy` and `/terms`, linked in the footer, drafted from what the site says: data collected through WhatsApp with
consent; farmers can view, correct or delete their data; data not sold or shared without permission; buyers see only
farmer information the farmer agreed to share; no guarantee of sale, price or payment; Ezina doesn't move money.
`[TODO]` for legal entity name, address and governing law. Contact hello@ezina.ai. A visible "draft pending legal
review" note at the top of each. **The privacy policy must stay at https://www.ezina.ai/privacy** (Meta WhatsApp
Business verification needs a stable URL).

### SEO and sharing
Title "Ezina | AI-Powered Agri Trade"; meta description adapted from the original site; matching Open Graph and
Twitter tags, `twitter:card` = `summary_large_image`; 1200×630 OG image at https://www.ezina.ai/og-image.png
(logo + "AI-Powered Agri Trade" + "Verified truth before you sell", under 300 KB); favicon, sitemap.xml, robots.txt,
canonical https://www.ezina.ai, Organization JSON-LD.

### Deliverables
Working monorepo (`pnpm install`, `pnpm dev`, `pnpm build` → static export); README (edit content, toggle appLive,
build, deploy to Cloudflare Pages); a list of every `[TODO]` placeholder.

### Working agreement
Before a larger build or redesign, show the outline and the colour/typography direction for a quick check first.

---

## 2. Decisions made during the build (2026-11-27)

- **Location:** `ezina-web/` next to `ezina-connect/`; its own pnpm workspace and lockfile. Cloudflare Pages root
  directory `ezina-web`, output `apps/web/out`.
- **Versions:** Next 16.4, React 19.3, Tailwind 4.3 (CSS `@theme` tokens), TypeScript 5.9, ESLint 9 (flat config).
- **Bundler:** `dev` and `build` use `--webpack`; Turbopack fails on Windows + pnpm to load `lightningcss`.
- **Brand (from the original stylesheet):** navy `#0c1e34`, navy-deep `#081627`, cream `#fdfcf7`, orange `#fc4a1a`
  (logo/accents only), orange-soft `#ff9a7a`, ink `#1d2a38`, muted `#5a6570`, line `#e8e2d4`, ok `#1e7a46`.
  Added for WCAG AA: button orange `#d4370c` (white text), orange text on light `#c2330b`, warn `#a34a06`.
  Fonts: Libre Franklin (headings), Inter (body), self-hosted via `next/font`. Tokens: `packages/ui/src/theme.css`.
- **Logo (second pass):** the official file www.ezina.ai/logo.png everywhere (header 56px tall, footer 64px, chat
  avatar, favicon, OG image), with `alt="Ezina"` and explicit width/height. Owner-approved: only the empty cream margin
  is trimmed; no recolouring or cropping of the artwork. It keeps its own cream background, so it shows as a cream tile
  on the navy footer. `public/logo.png` is the untouched full file.
- **Images:** generated from the original site's files: founder photos 256px WebP + JPEG; icons; OG image.
- **Stats strip (second pass):** 1K+ Farmers Connected, 10+ Crop Varieties, 24/7 AI-Powered, 3+ Countries, confirmed
  by the owner on 2026-11-27. Each is `{ display, countTo, label }` in `site.ts`; `display` is in the static HTML and the
  count-up (client component, IntersectionObserver) runs only without reduced motion. The validation copy no longer
  says "pre-product"; the 24 farmers are "the structured research record".
- **Validation evidence:** *(superseded by the validation-story stepper below)* previously showed the original site's
  20/20 questionnaire findings alongside the 24 farmers; now only the 24-farmers line is shown, as the owner asked.
- **FAQ answers:** the original site had no FAQ; answers are drawn from its copy (Verified Opportunity Standard,
  How Ezina earns, farmer Control card, validation footprint). Kenya and India are named as expansion markets
  (from the founder bio).
- **Dropped:** the original "Agricultural Indices" table (illustrative values only) and the long roadmap. ("Why choose
  Ezina" was dropped at first, then re-added at the owner's request: see below.)
- **Chat mockups:** no real prices; chat 2 uses `[TODO]` price/source slots. Location is shown as a WhatsApp pin
  (never typed GPS), matching the backend rule.
- **Early access removed (second pass, owner request):** no early-access section, form, env variable or links; the
  `appLive` flag is gone. `getStartedUrl: null` renders every Get Started as a disabled button (`disabled`,
  `aria-disabled="true"`, no href) with a "Coming soon" badge; a URL turns them all into links. `loginUrl` likewise.
  There is no /contact page, so there was no enquiry dropdown to change.
- **Hero (fourth pass, owner request):** photo hero in the style of eiziba.com / `docs/refs/hero1.png` (references
  only; nothing copied). Full-bleed photo of a cornfield at sunset (Pexels 33443252, free Pexels licence; chosen by the
  owner) under a deep-green overlay that is darkest behind the copy and lighter on the right so the sky shows. Left:
  glass "AI-Powered Agri Trade" pill, white headline with "intelligence" in a light orange `#ffa27f`, subtext, glass
  "Coming soon" Get Started (`onDark`), farmer WhatsApp link, and inline count-up stats. Right: three glass cards
  (`hero.cards` in `site.ts`). Phones: copy, then stats (2×2), then cards. The photo is pre-cropped WebP via `<picture>`:
  750px tall crop for phones (about 105 KB), 1280/1920px wide crops (about 100/215 KB). The reference images live in
  `ezina-web/docs/refs/` (moved out of `public/` so they are never deployed). The WhatsApp section is unchanged in
  this pass, at the owner's request.
- **WhatsApp demo (fifth pass, owner brief):** "See how farmers use Ezina" is now ONE large phone plus 3 interactive
  steps (Farmer asks a question → Ezina gets the details → Verified price reference), replacing the three phones in a
  row. `components/home/DemoShowcase.tsx` (client) + `components/ChatPhone.tsx` (phone frame, bubbles, typing).
  - **Phone height (owner, 2026-11-27):** version B (+10%, chosen from a side-by-side preview), then another +10% →
    max **678px**:
    - phones: `min(678px, 82svh, 100svh-254px)`
    - tablets (md): `min(678px, 100svh-386px)`, because the heading and intro sit above the phone there
    - from lg: `min(678px, 100svh-168px)`

    Section padding is `py-4 sm:py-6 lg:py-7`. Results: 1440×900 → 678px, 1366×768 → 600px, 1280×720 → 552px,
    1024×768 → 600px, 768×1024 → 638px, 390×844 → 590px, 375×667 → 413px. The section fits one screen at all of
    them. This supersedes the sizes in the next note.
  - **Seventh pass (fits one screen):** the section is `min-h-[calc(100svh-72px)]`, centred, `py-6 sm:py-10 lg:py-12`.
    The phone is sized by height with `aspect-[9/18]`: `min(560px, 70svh, 100svh-270px)` below `lg`,
    `min(560px, 100svh-210px)` from `lg` (1440×900 gives 280×560, 1280×720 gives 255×510, 375×667 gives about
    215×397). Inside, everything is scaled down: 13px chat text, 44px header, 32px status bar, 36px input bar. Each step
    plays **its own messages** (not cumulative) in a chat box that scrolls internally (`.chat-scroll`, thin
    scrollbar): it starts at the top for each step and smooth-scrolls to the newest message while animating, and the
    page never scrolls. The static HTML still contains the whole conversation (all steps). The left column is
    compact, with one-line step descriptions. Phones: the intro is hidden below `sm` and the tabs are numbered dots plus
    the active step's title. Cards are positioned in % of the phone height, so they stay within its top and bottom. The
    floating mobile WhatsApp shortcut is hidden while the demo is on screen (`html[data-demo-in-view]`), so it can't
    cover the tabs. Step 3's duplicate question "Want me to find you a verified buyer?" was removed (step 4 asks it).
    Verified at 1440×900, 1366×768, 1280×720, 768×1024 and 375×667.
  - **Sixth pass:** 4 steps (added "Farmer chooses what's next": Ezina's question with 3 WhatsApp-style quick-reply
    buttons, a brief tap highlight on "Find a verified buyer", the farmer's reply, typing, Ezina's confirmation) and a
    4th card ("Matching buyers"). The phone is now straight (no rotation) on all sizes. Messages support `buttons` and
    `tap` in `site.ts`. Step tabs: 2×2 on phones, 4 in a row from `sm`, a vertical list from `lg`.
  - Desktop: heading + steps (tabs, accent bar on the active one) on the left; the phone on the right with a
    blurred orange/green blob, a fading dot grid and 4 floating cards (Buyer verified, P9.50–P11.00/kg, Uncertain,
    Matching buyers) that appear in sync with the steps and overlap only the phone's edge (~20px). Phones: heading →
    phone → step tabs; swiping on the phone changes step; cards hidden below `md`.
  - The chat is cumulative: each step adds its messages; Ezina's replies come after a typing indicator. Autoplay
    (~5 s per step) starts when the section scrolls into view, pauses on hover/focus and while off-screen; clicks and
    arrow keys select steps (`role="tab"`, `aria-selected`, roving tabindex; chat list is `aria-live="polite"`).
  - Static HTML / no JS / reduced motion: the full conversation (last step) and all cards are shown; reduced motion
    never autoplays and shows each step's final state. Animations use transform/opacity only.
  - Phone: thin bezel, dynamic island, status bar (time, signal, Wi-Fi, battery), green header with back arrow, Ezina
    logo avatar (from logo.png), "online", video/voice/menu SVG icons; bubbles support `*bold*`, emoji and `\n`; a
    location bubble; decorative input bar. Chat wallpaper: soft topographic contour lines as an inline SVG tile
    (inspired by `docs/refs/wa3.jpg`, which is another company's promo graphic and was moved out of `public/`).
  - Content (`demo` in `site.ts`): the price "P9.50–P11.00/kg from 2 verified buyers this week" and quantity 500 kg
    are **example figures requested by the owner**, labelled under the phone "Example conversation · example figures".
    They are not market data. Replace them if Ezina publishes real references.
- **Why choose Ezina + How Ezina earns (owner request, overrides the earlier "merge/remove Why choose"):**
  - Order: … → Validation story → Why choose Ezina → How Ezina earns (`#pricing`) → FAQ → Founders → Closing. The header
    nav (and mobile menu and footer, which share `nav`) has a "Pricing" link to `/#pricing`.
  - Why choose: the 5 titles come from the original site, which had no descriptions; the one-liners are drawn from
    the site's own copy. The original intro "More than a marketplace." is left out (Ezina is not a marketplace); its
    second sentence is used. Layout: 1 column of compact rows on phones, 2 from `sm`, 3 + 2 centred from `lg`, 5 in a
    row from `xl`; it fits one screen at 375/768/1024/1440. Cards lift on hover.
  - How Ezina earns: pricing-style cards with no prices and no Get Started, using the original wording (Buyers pay
    for intelligence / Institutions pay for scale / Farmers start free). The Buyers card is emphasised (2px orange
    border, "For buyers" label, filled CTA); Farmers has a "Free" badge. Equal heights, CTAs aligned, plus two trust
    statements. "Talk to us" uses `contactHref` in `site.ts` (now "/contact"). The old roadmap line ("Ezina Market and
    Ezina Trust first…") is no longer shown.
- **/contact "Talk to us" (owner request; built new, since there was no earlier contact page):** a dark navy section
  modelled on a "Get in touch" form layout (pill fields; first/last and phone/email in pairs; full-width company and
  message; an outlined pill button), in Ezina colours and fonts, with **visible labels** (the reference used
  placeholders only) and **no CAPTCHA**. Fields: first name*, last name*, phone (optional, validated if given), work
  email* (validated), company*, message* (20–2000 characters, with a counter), and a hidden honeypot `website` (if it
  is filled, the form shows success and sends nothing).
  - Plain-TypeScript validation (no form library, to keep JavaScript small): errors on blur and on submit, the first
    invalid field focused, `aria-invalid` and `aria-describedby`.
  - States: idle → sending (spinner, disabled) → success (check animation, "Complete", "Thank you! We'll be in touch
    shortly.", "Send another message") or error (input kept, generic message). A 400 maps errors onto fields.
  - Submit logic: `lib/contact.ts` (`submitContact`). `NEXT_PUBLIC_CONTACT_MODE` = mock (default: ~1 s, console log,
    success) or api (POST JSON, 15 s timeout, 200/400/other). The contract is in the README. `phone` was added to the
    draft payload because the form collects it.
  - Aside: email, farmer WhatsApp link, "Where we work: Gaborone · Bengaluru · Nairobi" (`[TODO: confirm]` in
    `site.ts`), LinkedIn/X icons. Title "Talk to us | Ezina", meta description, in `sitemap.xml`.
  - Every "Talk to us" on the site (audience cards, pricing cards, closing CTA) links to /contact. The privacy policy
    text now describes what the form collects. The header is now opaque cream: the translucent version lost contrast
    over the dark contact page.
  - On-scroll entrance: `components/Reveal.tsx` arms items (opacity 0 + 16px) only with JavaScript, without reduced
    motion and when the group is below the fold, then fades and rises them ~80 ms apart when they come into view.
- **Validation story stepper (owner request):** the `[TODO]` placeholders are replaced by an **illustrative scenario
  with example figures provided by the owner** (smallholder maize farmer, Trans Nzoia, Kenya; ~50 bags; broker
  KES 2,800 vs matched reference KES 3,300 per bag; a verified miller in Eldoret, unnamed). It is labelled
  "Illustrative scenario · example figures" next to the heading, and the card footer always says "This scenario shows
  how Ezina works. It is not a record of a completed transaction." No real person or company is named. Kenya is an
  expansion market, not part of the validation footprint, which is one more reason it stays labelled illustrative.
  Layout: card on the RIGHT, so the stepper sections alternate (WhatsApp demo right, What buyers receive left, story
  right). 3 steps:
  - The Challenge: maize icon, location/crop chips, problem points with amber icons, broker-offer tag with "?".
  - What Ezina Did: 4 actions, each with a spinner that completes into a drawn check; payment history is an amber chip.
  - The Outcome: price bars growing from 0 (scaleX), the challenge and uncertainty notes, "Recorded for future
    matches".

  Auto-advance every 6 s. The real evidence line sits under the steps: "Early validation: 24 farmers (…)". The 20/20
  questionnaire findings and "what we are proving next" are no longer shown on the page. Stepper behaviour is now
  shared by the hook `components/useStepper.ts` (start in view, progress-bar auto-advance, pause on hover, focus or
  off-screen, swipe, hide the floating mobile WhatsApp button), used by `BuyersShowcase` and `StoryShowcase`.
- **"What buyers receive" stepper (owner request):** replaces the report and opportunity shown one after another. It
  uses the same stepper as the WhatsApp demo but mirrored: the card on the left, the heading and steps on the right
  (phones: heading → card → tabs). Shared `components/StepTabs.tsx` (also used by the WhatsApp demo): vertical list
  from `lg`, a row of tabs from `sm`, numbered dots plus the active title on phones; arrow/Home/End keys; optional
  progress bar. `components/home/BuyersShowcase.tsx` has 3 steps:
  - Buyer verification report: ABC Fresh Produce Ltd, 5 rows with status chips that resolve after a shimmer; confirmed
    check marks draw themselves.
  - Verified opportunity: Fresh Tomatoes, 2,000 kg, Kweneng; "Buyer identity: Confirmed" pulses once.
  - Evidence & uncertainty: checked items, then uncertain ones.

  Auto-advance is driven by the active tab's CSS progress bar (5 s, `animationend` → next step). It is paused on
  hover, focus or when off-screen, and never runs with reduced motion. All three cards are in the static HTML (inactive
  ones `hidden`), in their final state unless `.bx-run` animates them. The card height is
  `min(540px, 100svh-250px)` (phones/tablet) or `min(540px, 100svh-200px)` (lg), with internal scrolling when needed;
  the section is one screen tall. A floating note per step: "3 of 5 checks confirmed" / "Price needs review" /
  "Evidence attached to every claim". The old report summary and "Verified Opportunity Standard" block were dropped.
  `StatusPill.tsx` was removed (unused). The floating mobile WhatsApp shortcut is also hidden while this section is
  on screen (`html[data-buyers-in-view]`).
- **"What is Ezina for?" (audiences, owner request):** four equal-height cards replace the two-card layout and the
  "Farmers join free on WhatsApp" strip: For farmers (with a "Free" badge and "The essential service is free."), For
  buyers, For institutions, Export partners. Titles and points come from the original www.ezina.ai "What is Ezina
  for?" section; each card's 3 points are taken from its own sentence there. No Get Started: the links are "Chat on
  WhatsApp" (farmers), "What buyers receive" (to `#what-buyers-receive`) and "Talk to us" (mailto with a subject line).
  The ids `#buyers` and `#partners` are kept for the header nav. 1 column on phones, 2×2 from `md` (equal rows), 4 in
  a row from `xl` (1280px). All text and links are in `audiences` in `site.ts`.
  **Update:** the Institutions and Export partners links are now "See how it works for institutions/exporters" →
  `/#pricing`, each with `data-highlight` (`institutions-plan` / `buyers-plan`: exporters are served by the buyer
  offer). `components/PlanHighlighter.tsx` waits until that "How Ezina earns" card is on screen, then shows a one-off
  orange ring: a pulse fading over 1.5 s, or a static 2 s ring under reduced motion. Without JS the link still jumps to
  `#pricing`. In-page anchors use `scroll-margin-top: 73px` (the header height). On phones the institutions card can
  be below the fold after the jump; its ring then plays when it scrolls into view.
- **Header action (owner request):** the header shows a primary "Talk to us" button (`header.talkToUs` → `contactHref`)
  instead of "Get Started", plus one at the bottom of the mobile menu. Get Started / Coming soon is hidden in the header
  only (still in the hero and closing CTA); `getStartedUrl` is unchanged, so it can return when the app launches.
- **JavaScript:** small client components only (mobile menu close, stat count-up, WhatsApp demo). Everything else is
  server-rendered HTML.
- **Legal copy** lives in `site.ts` (`legal.privacy`, `legal.terms`); it names Meta/WhatsApp, hosting/database and an
  AI language provider as processors (`[TODO]` to confirm the list).
- **Metadata:** `lib/metadata.ts` builds the full OG/Twitter set per page, because Next replaces (not merges) those
  objects in child routes.

## 3. Checks to run after changes

```bash
pnpm lint && pnpm typecheck && pnpm build
grep -rIn "ezina.tech" . --exclude-dir=node_modules --exclude-dir=.next --exclude-dir=out   # only the LinkedIn URL
grep -n "\[TODO" apps/web/content/site.ts                                                   # open placeholders
```
Check the result on a 390px-wide phone viewport and a desktop viewport.
