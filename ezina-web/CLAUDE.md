# Ezina web (www.ezina.ai)

Marketing site for Ezina, "AI-Powered Agri Trade". pnpm workspace: `apps/web` (Next.js App Router + Tailwind v4,
static export for Cloudflare Pages), `packages/ui` (brand tokens, Logo, ButtonLink), `packages/config` (Tailwind base,
tsconfig, ESLint). A future `apps/app` (app.ezina.ai dashboard) will reuse `@ezina/ui`; don't build it unless asked.

**Always follow `docs/website-spec.md` (the owner's brief + build decisions). Read it before making changes.**
Status, open work and decisions are also tracked in `../docs/progress.md`.

## Rules (do not break)

- **Ezina is not a marketplace.** Never use "shop", "cart", "buy now", "listings for sale". Ezina moves no money and
  takes no cut.
- **Honest tone:** say what is verified and what is uncertain; verification never guarantees a sale, price or payment.
- **Never invent** facts, customers, numbers, prices, quotes or results. Missing content → `[TODO: ...]` placeholder,
  and list every placeholder for the owner at the end of the task.
- **Show, don't describe:** examples, chat mockups, sample reports and step visuals over abstract claims.
- **All copy, stats, FAQs, links, flags and legal text live in `apps/web/content/site.ts`.** Components only render it.
- **Domain is www.ezina.ai only** (canonical, OG, sitemap, robots, JSON-LD, email hello@ezina.ai). The only allowed
  "ezina.tech"-like string is the LinkedIn URL `linkedin.com/company/ezina-tech`.
- All content must be in the static HTML (no client-only rendering). Keep JavaScript minimal; mobile-first, slow networks.
- Accessible: semantic HTML, alt text on every image, WCAG AA contrast (white text only on `orange-strong`, orange
  text only as `orange-ink`), keyboard-friendly.
- `/privacy` must stay at that URL (Meta WhatsApp Business verification). Legal pages keep the "draft pending legal
  review" note until the owner says otherwise.
- Self-contained: no imports from `ezina-connect/` or anything outside `ezina-web/`.
- For a larger build or redesign, show the outline and visual direction for a quick check before building.

## Commands (run in `ezina-web/`; Node 22 + pnpm 10)

```bash
pnpm install
pnpm dev          # next dev --webpack, http://localhost:3000
pnpm build        # static export → apps/web/out
pnpm lint && pnpm typecheck
```
Use `--webpack` (already in scripts): Turbopack fails on Windows + pnpm loading `lightningcss`.

## After every task

Run lint, typecheck and build; check that `ezina.tech` appears only in the LinkedIn URL; list open `[TODO` placeholders;
update `docs/website-spec.md` (decisions) and `../docs/progress.md`.
