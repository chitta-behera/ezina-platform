"use client";

import { useRef, useState, type ChangeEvent, type FocusEvent, type FormEvent } from "react";
import { cn } from "@ezina/ui";
import { contactPage as c } from "@/content/site";
import { submitContact, type ContactFields } from "@/lib/contact";

type FieldName = keyof ContactFields;
type Values = Record<FieldName, string> & { website: string };
type State = "idle" | "sending" | "success" | "error";

const ORDER: FieldName[] = ["firstName", "lastName", "phone", "email", "company", "message"];
const EMPTY: Values = { firstName: "", lastName: "", email: "", phone: "", company: "", message: "", website: "" };
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const PHONE_RE = /^[+()\d\s.-]{7,24}$/;

/** Plain-TypeScript validation (no form library: keeps the page's JavaScript small). */
function validate(name: FieldName, raw: string): string | undefined {
  const v = raw.trim();
  switch (name) {
    case "phone":
      if (!v) return undefined; // optional
      return PHONE_RE.test(v) && (v.match(/\d/g)?.length ?? 0) >= 7 ? undefined : c.errors.phone;
    case "email":
      if (!v) return c.errors.required;
      return EMAIL_RE.test(v) ? undefined : c.errors.email;
    case "message":
      if (!v) return c.errors.required;
      if (v.length < c.messageMin) return c.errors.messageMin;
      if (v.length > c.messageMax) return c.errors.messageMax;
      return undefined;
    default:
      return v ? undefined : c.errors.required;
  }
}

/**
 * "Talk to us" form. Inline errors on blur and on submit (first invalid field focused); labels, aria-invalid and
 * aria-describedby on every field; a hidden honeypot (no CAPTCHA). States: idle → sending → success | error.
 * Submission goes through lib/contact.ts (mock now, API later).
 */
export function ContactForm() {
  const [values, setValues] = useState<Values>(EMPTY);
  const [touched, setTouched] = useState<Partial<Record<FieldName, boolean>>>({});
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const [attempted, setAttempted] = useState(false);
  const [state, setState] = useState<State>("idle");
  const refs = useRef<Partial<Record<FieldName, HTMLInputElement | HTMLTextAreaElement | null>>>({});
  const successRef = useRef<HTMLHeadingElement>(null);

  const errorFor = (name: FieldName) => serverErrors[name] ?? ((touched[name] || attempted) ? validate(name, values[name]) : undefined);

  const onChange = (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setValues((v) => ({ ...v, [name]: value }));
    if (serverErrors[name])
      setServerErrors((prev) => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
    if (state === "error") setState("idle");
  };
  const onBlur = (e: FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const name = e.target.name as FieldName;
    if (ORDER.includes(name)) setTouched((t) => ({ ...t, [name]: true }));
  };

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (state === "sending") return;
    setAttempted(true);
    const invalid = ORDER.filter((n) => validate(n, values[n]));
    if (invalid.length) {
      refs.current[invalid[0]!]?.focus();
      return;
    }
    // Honeypot filled (a bot): pretend it worked, send nothing.
    if (values.website.trim()) {
      setState("success");
      requestAnimationFrame(() => successRef.current?.focus());
      return;
    }
    setState("sending");
    const fields: ContactFields = {
      firstName: values.firstName,
      lastName: values.lastName,
      email: values.email,
      phone: values.phone,
      company: values.company,
      message: values.message,
    };
    const res = await submitContact(fields);
    if (res.ok) {
      setState("success");
      requestAnimationFrame(() => successRef.current?.focus());
      return;
    }
    if (res.errors && Object.keys(res.errors).length) {
      setServerErrors(res.errors);
      setState("idle");
      const first = ORDER.find((n) => res.errors?.[n]);
      if (first) requestAnimationFrame(() => refs.current[first]?.focus());
      else setState("error");
      return;
    }
    setState("error");
  }

  const reset = () => {
    setValues(EMPTY);
    setTouched({});
    setServerErrors({});
    setAttempted(false);
    setState("idle");
    requestAnimationFrame(() => refs.current.firstName?.focus());
  };

  if (state === "success") {
    return (
      <div role="status" className="flex flex-col items-center rounded-[28px] border border-navy-line bg-navy-card px-6 py-12 text-center sm:py-16">
        <span className="contact-check grid h-20 w-20 place-items-center rounded-full bg-ok text-white shadow-[0_0_0_10px_rgb(30_122_70/0.18)]">
          <svg aria-hidden="true" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
            <path className="contact-check-path" d="M5 12.5l4.5 4.5L19 7.5" />
          </svg>
        </span>
        <p className="mt-6 text-[12.5px] font-bold uppercase tracking-[0.18em] text-[#8fd4ac]">{c.success.label}</p>
        <h2 ref={successRef} tabIndex={-1} className="mt-2 font-display text-[24px] font-bold text-white outline-none sm:text-[28px]">
          {c.success.heading}
        </h2>
        <button type="button" onClick={reset} className="mt-6 text-[15.5px] font-semibold text-orange-soft underline underline-offset-4 hover:text-white">
          {c.success.again}
        </button>
      </div>
    );
  }

  const sending = state === "sending";
  const msgLen = values.message.trim().length;

  return (
    <form noValidate onSubmit={onSubmit} aria-describedby={state === "error" ? "contact-error" : undefined} className="relative">
      <div className="grid gap-x-5 gap-y-5 sm:grid-cols-2">
        {renderField({ name: "firstName", autoComplete: "given-name" })}
        {renderField({ name: "lastName", autoComplete: "family-name" })}
        {renderField({ name: "phone", type: "tel", autoComplete: "tel", inputMode: "tel" })}
        {renderField({ name: "email", type: "email", autoComplete: "email", inputMode: "email" })}
        {renderField({ name: "company", autoComplete: "organization", wide: true })}
        {renderField({ name: "message", multiline: true, wide: true })}
      </div>

      {/* Honeypot: hidden from people and assistive tech. Not a CAPTCHA. */}
      <div aria-hidden="true" className="absolute -left-[9999px] top-0 h-px w-px overflow-hidden">
        <label>
          Website
          <input name="website" type="text" tabIndex={-1} autoComplete="off" value={values.website} onChange={(e) => setValues((v) => ({ ...v, website: e.target.value }))} />
        </label>
      </div>

      {state === "error" && (
        <p id="contact-error" role="alert" className="mt-6 flex gap-2.5 rounded-[16px] border border-[#ff9a7a]/50 bg-[#ff9a7a]/10 px-4 py-3 text-[15px] font-semibold text-[#ffc7b6]">
          <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" className="mt-0.5 shrink-0">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7.5v5.5M12 16.5v.01" />
          </svg>
          {c.errors.generic}
        </p>
      )}
      {attempted && state !== "error" && ORDER.some((n) => errorFor(n)) && (
        <p className="mt-5 text-[14.5px] font-semibold text-[#ffc7b6]">{c.errors.summary}</p>
      )}

      <div className="mt-8 flex flex-col items-center gap-4">
        <button
          type="submit"
          disabled={sending}
          aria-disabled={sending}
          className={cn(
            "inline-flex h-14 min-w-[220px] items-center justify-center gap-3 rounded-full border-2 border-white px-8 text-[18px] font-semibold text-white transition-colors",
            "hover:border-orange-strong hover:bg-orange-strong focus-visible:outline-offset-4 disabled:cursor-wait disabled:opacity-80",
          )}
        >
          {sending && <span aria-hidden="true" className="h-5 w-5 animate-spin rounded-full border-2 border-white/40 border-t-white" />}
          {sending ? c.sending : c.submit}
        </button>
        <p className="text-[13.5px] text-[#a9b6c4]">
          {c.privacyNote}{" "}
          <a href="/privacy" className="text-[#dde4ec] underline underline-offset-2 hover:text-white">
            {c.privacyLink}
          </a>
        </p>
      </div>
    </form>
  );

  /** Renders one labelled field (a plain function, not a component, so inputs keep focus between renders). */
  function renderField({
    name,
    type = "text",
    autoComplete,
    inputMode,
    multiline = false,
    wide = false,
  }: {
    name: FieldName;
    type?: string;
    autoComplete?: string;
    inputMode?: "tel" | "email" | "text";
    multiline?: boolean;
    wide?: boolean;
  }) {
    const f = c.fields[name];
    const err = errorFor(name);
    const id = `contact-${name}`;
    const optional = "optional" in f ? f.optional : undefined;
    const describedBy = [err ? `${id}-error` : null, name === "message" ? `${id}-count` : null].filter(Boolean).join(" ") || undefined;
    const base = cn(
      "block w-full border bg-[#0a1a2d] px-6 text-[15.5px] text-white placeholder:text-[#8597aa] transition-colors",
      "focus:border-orange-soft focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-soft",
      err ? "border-[#ff9a7a]" : "border-navy-line hover:border-[#2d5779]",
    );
    const common = {
      id,
      name,
      value: values[name],
      onChange,
      onBlur,
      disabled: sending,
      required: !optional,
      "aria-required": !optional,
      "aria-invalid": !!err,
      "aria-describedby": describedBy,
      placeholder: f.placeholder,
    };
    return (
      <div key={name} className={cn(wide && "sm:col-span-2")}>
        <label htmlFor={id} className="mb-2 flex items-baseline justify-between gap-3 pl-6 text-[13.5px] font-semibold text-[#c3cedb]">
          <span>{f.label}</span>
          {optional && <span className="pr-6 text-[12.5px] font-normal text-[#8597aa]">{optional}</span>}
        </label>
        {multiline ? (
          <textarea
            {...common}
            ref={(el) => {
              refs.current[name] = el;
            }}
            rows={5}
            maxLength={c.messageMax + 200}
            className={cn(base, "min-h-[150px] resize-y rounded-[26px] py-4 leading-relaxed")}
          />
        ) : (
          <input
            {...common}
            ref={(el) => {
              refs.current[name] = el;
            }}
            type={type}
            autoComplete={autoComplete}
            inputMode={inputMode}
            className={cn(base, "h-[52px] rounded-full")}
          />
        )}
        <div className="mt-1.5 flex justify-between gap-3 px-6 text-[13px]">
          <span id={`${id}-error`} className="font-semibold text-[#ffb59f]">
            {err}
          </span>
          {name === "message" && (
            <span id={`${id}-count`} className={cn("shrink-0 tabular-nums", msgLen > c.messageMax || (msgLen > 0 && msgLen < c.messageMin) ? "text-[#ffb59f]" : "text-[#8597aa]")}>
              {msgLen} / {c.messageMax}
              <span className="sr-only"> characters (minimum {c.messageMin})</span>
            </span>
          )}
        </div>
      </div>
    );
  }
}
