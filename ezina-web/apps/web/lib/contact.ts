/**
 * Contact form submission ("Talk to us"). All submit logic lives here so the backend can be connected with a
 * config change only:
 *
 *   NEXT_PUBLIC_CONTACT_MODE     "mock" (default) | "api"
 *   NEXT_PUBLIC_CONTACT_API_URL  endpoint for "api" mode (absolute URL, or a same-origin path)
 *
 * Both are read at build time (static export). See README "Contact form API contract".
 *
 * Request (api mode): POST JSON
 *   { firstName, lastName, email, phone?, company, message, pageUrl, submittedAt }
 * Responses:
 *   200 { ok: true }
 *   400 { ok: false, errors: { "<field>": "<message>" } }   → shown next to the fields
 *   anything else (5xx, network error, timeout)            → generic error
 */

export type ContactFields = {
  firstName: string;
  lastName: string;
  email: string;
  /** Optional. Not in the original contract draft; included because the form collects it. */
  phone?: string;
  company: string;
  message: string;
};

export type ContactPayload = ContactFields & {
  /** The page the form was sent from. */
  pageUrl: string;
  /** ISO-8601 timestamp, set in the browser. */
  submittedAt: string;
};

export type ContactResult = { ok: boolean; errors?: Record<string, string> };

const MODE = (process.env.NEXT_PUBLIC_CONTACT_MODE ?? "mock").trim().toLowerCase() === "api" ? "api" : "mock";
const API_URL = (process.env.NEXT_PUBLIC_CONTACT_API_URL ?? "").trim();
const TIMEOUT_MS = 15_000;

export const contactConfig = { mode: MODE, apiUrl: API_URL } as const;

export function buildPayload(data: ContactFields): ContactPayload {
  const phone = data.phone?.trim();
  return {
    firstName: data.firstName.trim(),
    lastName: data.lastName.trim(),
    email: data.email.trim(),
    ...(phone ? { phone } : {}),
    company: data.company.trim(),
    message: data.message.trim(),
    pageUrl: typeof window !== "undefined" ? window.location.href : "",
    submittedAt: new Date().toISOString(),
  };
}

export async function submitContact(data: ContactFields): Promise<ContactResult> {
  const payload = buildPayload(data);

  if (MODE === "mock") {
    // No backend yet: simulate a successful request so the whole UX can be tried.
    await new Promise((r) => setTimeout(r, 1000));
    console.info("[contact:mock] would POST", payload);
    return { ok: true };
  }

  if (!API_URL) {
    console.error("[contact] NEXT_PUBLIC_CONTACT_MODE is 'api' but NEXT_PUBLIC_CONTACT_API_URL is empty");
    return { ok: false };
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (res.status === 200) return { ok: true };
    if (res.status === 400) {
      const body = (await res.json().catch(() => null)) as { errors?: unknown } | null;
      const errors = body && typeof body.errors === "object" && body.errors !== null ? (body.errors as Record<string, string>) : undefined;
      return { ok: false, errors };
    }
    return { ok: false };
  } catch {
    return { ok: false }; // network error or timeout
  } finally {
    clearTimeout(timer);
  }
}
