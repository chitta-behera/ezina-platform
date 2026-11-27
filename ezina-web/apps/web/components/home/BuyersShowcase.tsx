"use client";

import type { CSSProperties, ReactNode } from "react";
import { cn } from "@ezina/ui";
import { verifiedExample as v, type Status } from "@/content/site";
import { StepTabs } from "../StepTabs";
import { useStepper } from "../useStepper";

const steps = v.steps;
const STEP_MS = 5000;

/**
 * "What buyers receive" stepper (mirrors the WhatsApp demo: card on the left, steps on the right).
 * - Static HTML / no JS / reduced motion: every card is in the HTML (only the active one is displayed) in its final
 *   state; reduced motion never auto-advances.
 * - With motion: starts when scrolled into view; the active tab's progress bar (CSS) drives auto-advance (~5 s) and
 *   pauses on hover, focus or when off-screen. Items inside each card animate in (CSS only, transforms and opacity).
 */
export function BuyersShowcase() {
  const { step, select, runKey, animate, progress, containerProps, touchProps } = useStepper({
    count: steps.length,
    durationMs: STEP_MS,
    fabKey: "buyersInView",
  });

  return (
    <div
      {...containerProps}
      className="grid w-full items-center gap-x-16 gap-y-3 [grid-template-areas:'head'_'card'_'steps'] sm:gap-y-6 lg:grid-cols-[1.08fr_0.92fr] lg:grid-rows-[auto_auto] lg:gap-y-7 lg:[grid-template-areas:'card_head'_'card_steps']"
    >
      <div className="max-w-xl [grid-area:head] lg:self-end">
        <p className="mb-1.5 text-[12px] font-bold uppercase tracking-[0.16em] text-orange-ink sm:mb-2.5 sm:text-[13px]">{v.eyebrow}</p>
        <h2 id="receive-heading" className="font-display text-[24px] font-bold leading-[1.12] tracking-[-0.02em] text-navy-deep sm:text-[32px] lg:text-[38px]">
          {v.heading}
        </h2>
        <p className="mt-3 hidden text-[15px] leading-relaxed text-muted sm:block lg:text-[16.5px]">{v.intro}</p>
      </div>

      <StepTabs
        steps={steps}
        active={step}
        onSelect={select}
        idPrefix="buyers"
        panelId="buyers-panel"
        label={v.stepsLabel}
        className="[grid-area:steps] lg:self-start"
        progress={progress}
      />

      {/* Card with backdrop and a floating note */}
      <div className="relative mx-auto w-full max-w-[560px] [grid-area:card] lg:mx-0 lg:max-w-none">
        <div aria-hidden="true" className="demo-dots pointer-events-none absolute -inset-x-10 -inset-y-8" />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-16 -left-10 h-[380px] w-[380px] rounded-full opacity-60 blur-3xl [background:radial-gradient(circle_at_60%_40%,rgb(252_74_26/0.5),transparent_60%),radial-gradient(circle_at_30%_75%,rgb(30_122_70/0.38),transparent_60%)] sm:h-[460px] sm:w-[460px]"
        />

        {/* Floating note (tablet and desktop): changes with the step */}
        <div aria-hidden="true" className="absolute -top-5 right-5 z-10 hidden md:block">
          <div key={`${step}-${runKey}`} className={cn("flex items-center gap-2 rounded-full border border-white/70 bg-white/95 py-2 pl-2 pr-3.5 text-[13px] font-semibold text-navy-deep shadow-[0_14px_32px_-14px_rgb(12_30_52/0.45)] backdrop-blur-md", animate && "bx-float-in")}>
            <span className={cn("grid h-6 w-6 place-items-center rounded-full", step === 1 ? "bg-warn-wash text-warn" : "bg-ok-wash text-ok")}>
              {step === 1 ? <WarnGlyph /> : <CheckGlyph />}
            </span>
            {v.floating[step]}
          </div>
        </div>

        <div
          {...touchProps}
          className="relative flex h-[min(540px,calc(100svh_-_250px))] flex-col overflow-hidden rounded-2xl border border-line bg-white shadow-[0_1px_2px_rgb(12_30_52/0.06),0_12px_24px_-12px_rgb(12_30_52/0.18),0_40px_70px_-30px_rgb(12_30_52/0.35)] lg:h-[min(540px,calc(100svh_-_200px))]"
        >
          <span aria-hidden="true" className="h-1 shrink-0 bg-[linear-gradient(90deg,var(--color-orange-strong),var(--color-orange)_60%,#ff9a7a)]" />
          <div
            id="buyers-panel"
            role="tabpanel"
            tabIndex={0}
            aria-labelledby={`buyers-tab-${step}`}
            aria-live="polite"
            className="chat-scroll relative flex min-h-0 flex-1 flex-col overflow-y-auto focus-visible:outline-offset-[-3px]"
          >
            {[ReportCard, OpportunityCard, EvidenceCard].map((Card, i) => (
              <div
                key={i === step ? `on-${runKey}` : `off-${i}`}
                hidden={i !== step}
                className={cn("flex flex-1 flex-col", i === step && animate && "bx-card-in bx-run")}
              >
                <Card />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------- Cards ---------- */

const item = (i: number, extra?: CSSProperties) => ({ className: "bx-item", style: { "--i": i, ...extra } as CSSProperties });

function CardHeader({ kicker, title, badge }: { kicker: string; title: string; badge: string }) {
  return (
    <div className="bx-grid border-b border-line px-5 pb-3 pt-4 sm:px-7 sm:pt-5">
      <p className="text-[11.5px] font-bold uppercase tracking-[0.14em] text-muted">{kicker}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 pr-0 md:pr-48">
        <h3 className="font-display text-[20px] font-bold leading-tight text-navy-deep sm:text-[22px]">{title}</h3>
        <span className="rounded-full border border-dashed border-warn px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-warn">{badge}</span>
      </div>
    </div>
  );
}

function ReportCard() {
  const r = v.report;
  return (
    <article aria-label={`${r.title}: ${r.name}`} className="flex flex-1 flex-col">
      <CardHeader kicker={v.steps[0]!.title} title={r.title} badge={r.badge} />
      <div className="flex-1 px-5 py-3 sm:px-7 sm:py-4">
        <div {...item(0)}>
          <p className="text-[12px] font-semibold uppercase tracking-[0.1em] text-muted">{r.buyerLabel}</p>
          <p className="mt-0.5 text-[16.5px] font-bold text-navy-deep">{r.name}</p>
          <p className="text-[14px] text-muted">{r.meta}</p>
        </div>
        <dl className="mt-3 divide-y divide-line border-y border-line">
          {r.rows.map((row, i) => (
            <div key={row.label} {...item(i + 1)} className="bx-item flex items-center justify-between gap-3 py-2">
              <dt className="text-[15px] text-ink">{row.label}</dt>
              <dd className="relative" style={{ "--d": `${520 + i * 300}ms` } as CSSProperties}>
                <span aria-hidden="true" className="bx-skel absolute inset-y-0 right-0 w-[118px] overflow-hidden rounded-full bg-[#eef0f2]" />
                <Chip status={row.status} label={row.value} resolve />
              </dd>
            </div>
          ))}
        </dl>
      </div>
      <Footnote i={7}>{r.note}</Footnote>
    </article>
  );
}

function OpportunityCard() {
  const o = v.opportunity;
  return (
    <article aria-label={`${o.label}: ${o.name}`} className="flex flex-1 flex-col">
      <CardHeader kicker={o.label} title={o.name} badge={o.badge} />
      <dl className="grid flex-1 content-start gap-3 px-5 py-4 sm:grid-cols-2 sm:px-7 sm:py-6">
        {o.facts.map((f, i) => (
          <div key={f.label} {...item(i)} className="bx-item rounded-[12px] border border-line bg-cream px-4 py-3">
            <dt className="text-[12px] font-semibold uppercase tracking-[0.1em] text-muted">{f.label}</dt>
            <dd className="mt-1.5">
              {"status" in f && f.status ? (
                <Chip status={f.status} label={f.value} pulse={f.label === "Buyer identity"} />
              ) : (
                <span className="text-[20px] font-bold text-navy-deep">{f.value}</span>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </article>
  );
}

function EvidenceCard() {
  const e = v.evidence;
  return (
    <article aria-label={`${e.label}: ${e.title}`} className="flex flex-1 flex-col">
      <CardHeader kicker={e.label} title={e.title} badge={v.opportunity.badge} />
      <div className="grid flex-1 content-start gap-5 px-5 py-4 sm:grid-cols-2 sm:px-7 sm:py-6">
        <div>
          <h4 {...item(0)} className="bx-item flex items-center gap-2 text-[15px] font-bold text-ok">
            <span className="grid h-6 w-6 place-items-center rounded-full bg-ok-wash"><CheckGlyph /></span>
            {e.checkedTitle}
          </h4>
          <ul className="mt-3 space-y-2.5">
            {e.checked.map((c, i) => (
              <li key={c} {...item(i + 1)} className="bx-item flex gap-2.5 text-[14.5px] leading-snug">
                <span className="mt-0.5 text-ok"><CheckGlyph /></span>
                <span>{c}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h4 {...item(e.checked.length + 1)} className="bx-item flex items-center gap-2 text-[15px] font-bold text-warn">
            <span className="grid h-6 w-6 place-items-center rounded-full bg-warn-wash"><WarnGlyph /></span>
            {e.uncertainTitle}
          </h4>
          <ul className="mt-3 space-y-2.5">
            {e.uncertain.map((u, i) => (
              <li key={u} {...item(e.checked.length + 2 + i)} className="bx-item flex gap-2.5 text-[14.5px] leading-snug">
                <span className="mt-0.5 text-warn"><WarnGlyph /></span>
                <span>{u}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <Footnote i={e.checked.length + e.uncertain.length + 2}>{e.note}</Footnote>
    </article>
  );
}

function Footnote({ i, children }: { i: number; children: ReactNode }) {
  return (
    <p {...item(i)} className="bx-item mt-auto flex gap-2 border-t border-line bg-cream/70 px-5 py-2.5 text-[13px] leading-snug text-muted sm:px-7">
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="mt-px shrink-0">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v5M12 7.5v.01" />
      </svg>
      <span>{children}</span>
    </p>
  );
}

/* ---------- Status chip ---------- */

const chipStyles: Record<Status, string> = {
  confirmed: "bg-ok-wash text-ok",
  checked: "bg-ok-wash text-ok",
  limited: "bg-warn-wash text-warn",
  review: "bg-warn-wash text-warn",
  "not-confirmed": "bg-[#eef0f2] text-[#4a5560]",
};

/** Status chip: colour + icon + text label (never colour alone). `resolve` = pops in after a shimmer; `pulse` = one ring. */
function Chip({ status, label, resolve = false, pulse = false }: { status: Status; label: string; resolve?: boolean; pulse?: boolean }) {
  const ok = status === "confirmed" || status === "checked";
  return (
    <span className={cn("relative inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[13px] font-semibold", chipStyles[status], resolve && "bx-chip", pulse && "bx-pulse")}>
      {ok ? (
        <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <path className={resolve ? "bx-draw" : undefined} d="M5 12.5l4.5 4.5L19 7.5" />
        </svg>
      ) : status === "not-confirmed" ? (
        <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
          <circle cx="12" cy="12" r="9" />
          <path d="M8 12h8" />
        </svg>
      ) : (
        <WarnGlyph />
      )}
      {label}
    </span>
  );
}

function CheckGlyph() {
  return (
    <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  );
}

function WarnGlyph() {
  return (
    <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3.5L2.5 20h19z" />
      <path d="M12 10v4.5M12 17.5v.01" />
    </svg>
  );
}
