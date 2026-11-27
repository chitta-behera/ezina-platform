# Ezina web

The marketing site for **www.ezina.ai** ("AI-Powered Agri Trade"), in a small pnpm workspace that will also hold
the future buyer/partner dashboard (`app.ezina.ai`).

```
ezina-web/
├─ apps/
│  └─ web/              # Marketing site: Next.js (App Router) + Tailwind, static export
│     ├─ content/site.ts   ← ALL copy, stats, FAQs, links and flags
│     ├─ app/              # routes: /, /privacy, /terms, sitemap.xml, robots.txt, icons
│     ├─ components/       # page sections and building blocks
│     └─ public/           # images, og-image.png, logo.png, Cloudflare _headers
├─ packages/
│  ├─ ui/               # @ezina/ui: brand tokens (theme.css), Logo, ButtonLink
│  └─ config/           # @ezina/config: shared Tailwind base, tsconfig, ESLint
└─ (future) apps/app    # buyer/partner dashboard at app.ezina.ai, reusing @ezina/ui; not built yet
```

This folder is self-contained: its own `package.json`, `pnpm-lock.yaml`, build and deployment. It does not depend
on the Python backend (`ezina-connect/`) or anything else in this repository.

## Requirements

- Node.js 20.9+ (22 recommended; see `.node-version`)
- pnpm 10 (`corepack enable pnpm`, or `npm i -g pnpm@10`)

## Commands (run in `ezina-web/`)

```bash
pnpm install       # install everything
pnpm dev           # http://localhost:3000
pnpm build         # static export to apps/web/out
pnpm start         # serve apps/web/out locally to check the export
pnpm lint          # ESLint across the workspace
pnpm typecheck     # TypeScript across the workspace
```

`dev` and `build` use webpack (`--webpack`). On Windows with pnpm, Turbopack (the Next 16 default) currently
fails to load Tailwind's native CSS engine (`lightningcss`); webpack builds the same output reliably.

## Editing content

Everything a visitor reads is in **`apps/web/content/site.ts`**: hero, stats, chat examples, audience cards,
steps, verification examples, validation story, pricing model, FAQ, founders, footer, legal pages, SEO text and links.
Components only render that file. You don't need to touch components to change copy.

- **Placeholders**: anything containing `[TODO` still needs real content. Search the file for `[TODO`.
- **Stats strip**: each stat has `confirmed`. Only `confirmed: true` stats are shown. Set the real value, then
  flip it to `true`.
- **Founder LinkedIn**: replace `"[TODO: LinkedIn URL]"` with the URL; the card switches to a link automatically.
- **FAQ**: edit `faq.items`. The FAQPage JSON-LD is generated from the same data (placeholders are left out).
- **Images**: founder photos live in `public/images/` as `.webp` + `.jpg` (256×256). Keep the same names, or
  change the `photo` path in `site.ts`.

Honesty rules (from the original site): always say what is verified and what is uncertain; verification never
guarantees a sale, price or payment; don't add customers, numbers, quotes or results that aren't real; Ezina is
not a marketplace (no "shop", "cart", "buy now" or "listings for sale").

## "Get Started" and "Log in"

In `content/site.ts`:

```ts
export const getStartedUrl: string | null = null; // e.g. `${links.appUrl}${links.signupPath}` when the app is live
export const loginUrl: string | null = null;      // e.g. `${links.appUrl}${links.loginPath}`
```

- `getStartedUrl: null`: every "Get Started" (header, hero, audience cards, closing) is a disabled button with a
  "Coming soon" badge. It has no link and can't be focused. Set a URL and they all become normal links.
- `loginUrl: null`: "Log in" is hidden in the header and mobile menu.

Rebuild and redeploy after changing them.

## Stats strip

`stats` in `content/site.ts`, one line per stat: `display` is the final text (always in the static HTML) and
`countTo` is the number the count-up animates to (`null` = static text, like "24/7").

## Contact form API contract (`/contact`, "Talk to us")

The form is frontend-only for now. All submit logic is in `apps/web/lib/contact.ts` (`submitContact(data)`), set by
two build-time environment variables (see `apps/web/.env.example`):

| Variable | Values | Effect |
|---|---|---|
| `NEXT_PUBLIC_CONTACT_MODE` | `mock` (default) / `api` | `mock`: no request; waits ~1 s, logs the payload to the browser console, shows success |
| `NEXT_PUBLIC_CONTACT_API_URL` | URL or same-origin path | Endpoint for `api` mode |

To connect the backend: set `NEXT_PUBLIC_CONTACT_MODE=api` and `NEXT_PUBLIC_CONTACT_API_URL=<endpoint>`, then
rebuild. If the endpoint is on another origin, it must allow CORS from `https://www.ezina.ai` (POST, `Content-Type`).

**Request:** `POST <NEXT_PUBLIC_CONTACT_API_URL>`, `Content-Type: application/json`, 15 s client timeout.

```json
{
  "firstName": "string (required)",
  "lastName": "string (required)",
  "email": "string (required, valid email)",
  "phone": "string (optional; omitted when empty)",
  "company": "string (required)",
  "message": "string (required, 20 to 2000 characters)",
  "pageUrl": "string (page the form was sent from)",
  "submittedAt": "string (ISO-8601, browser time)"
}
```

Values are trimmed. `phone` was added to the original draft contract because the form collects it.

**Responses:**

| Status | Body | Form shows |
|---|---|---|
| `200` | `{ "ok": true }` | Success panel ("Thank you! We'll be in touch shortly.") |
| `400` | `{ "ok": false, "errors": { "<field>": "<message>" } }` | Each message under its field (keys = the field names above); the first is focused |
| other, network error, timeout | — | "Something went wrong. Please try again or email hello@ezina.ai." (input kept) |

Spam: there is no CAPTCHA. A hidden honeypot field (`website`) is filled only by bots; when it is filled, the form
shows success and sends nothing. The backend should still validate every field, rate-limit, and never trust
`pageUrl` or `submittedAt`.

## Deploying apps/web to Cloudflare Pages

1. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git**, and pick this repository.
2. Build settings:
   - **Framework preset**: None
   - **Root directory**: `ezina-web`
   - **Build command**: `pnpm install --frozen-lockfile && pnpm build`
   - **Build output directory**: `apps/web/out`
3. Environment variables (Production and Preview):
   - `NODE_VERSION` = `22`
   pnpm is picked up from `packageManager` in `package.json`.
4. Optional: set **Build watch paths** to `ezina-web/*`, so backend-only commits don't trigger a deploy.
5. **Custom domains**: add `www.ezina.ai`. Redirect the apex `ezina.ai` to `https://www.ezina.ai` (Cloudflare
   Bulk Redirect or a redirect rule), since every canonical URL uses `www`.

Cloudflare Pages serves `privacy.html` at `/privacy`, so the privacy policy is at
**https://www.ezina.ai/privacy**, which is the URL to give Meta for WhatsApp Business verification.
`public/_headers` sets long cache lifetimes for hashed assets and basic security headers.

## SEO and sharing

- Title, description, canonical, Open Graph and Twitter tags: `seo` in `site.ts` and `lib/metadata.ts`.
- The official logo is www.ezina.ai/logo.png (a 1254×1254 JPEG). `public/logo.png` is that file as a real PNG,
  untouched. `public/images/logo.webp` (header/footer), `images/logo-avatar.webp` (chat profile picture),
  `app/icon.png`, `app/apple-icon.png` and `og-image.png` (1200×630, about 38 KB) were generated from it with only the
  empty margin trimmed. Replace the files to change them.
- `sitemap.xml` and `robots.txt` are generated from `app/sitemap.ts` and `app/robots.ts`.
- JSON-LD: Organization (in the layout) and FAQPage (in the FAQ section).
- Every URL uses `https://www.ezina.ai` (`siteUrl` in `site.ts`).

## Adding the dashboard later (`apps/app`)

Create `apps/app` as its own Next.js app, add `"@ezina/ui": "workspace:*"` and `"@ezina/config": "workspace:*"`,
import `@ezina/config/tailwind/base.css` and `@ezina/ui/theme.css` in its global CSS, and add `@ezina/ui` to
`transpilePackages`. It deploys as a separate Cloudflare project (or other host) at `app.ezina.ai`.
