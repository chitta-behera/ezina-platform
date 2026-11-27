"use client";

import type { CSSProperties, ReactNode } from "react";
import { cn } from "@ezina/ui";
import { validationStory as vs } from "@/content/site";
import { StepTabs } from "../StepTabs";
import { useStepper } from "../useStepper";

const steps = vs.steps;
const STEP_MS = 6000;

/**
 * Validation story stepper: an illustrative scenario (labelled), card on the RIGHT so the three stepper sections
 * alternate (WhatsApp demo: right, What buyers receive: left, Validation story: right).
 * Same behaviour as the other steppers (shared useStepper + StepTabs); every card is in the static HTML.
 */
export function StoryShowcase() {
  const { step, select, runKey, animate, progress, containerProps, touchProps } = useStepper({
    count: steps.length,
    durationMs: STEP_MS,
    fabKey: "storyInView",
  });

  return (
    <div
      {...containerProps}
      className="grid w-full items-center gap-x-16 gap-y-3 [grid-template-areas:'head'_'card'_'steps'_'evidence'] sm:gap-y-6 lg:grid-cols-[0.92fr_1.08fr] lg:grid-rows-[auto_auto_auto] lg:gap-y-6 lg:[grid-template-areas:'head_card'_'steps_card'_'evidence_card']"
    >
      <div className="max-w-xl [grid-area:head] lg:self-end">
        <div className="mb-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 sm:mb-2.5">
          <p className="text-[12px] font-bold uppercase tracking-[0.16em] text-orange-ink sm:text-[13px]">{vs.eyebrow}</p>
          <span className="rounded-full border border-dashed border-warn bg-warn-wash/60 px-2.5 py-0.5 text-[11.5px] font-bold text-warn">
            {vs.badge}
          </span>
        </div>
        <h2 id="story-heading" className="font-display text-[22px] font-bold leading-[1.12] tracking-[-0.02em] text-navy-deep sm:text-[32px] lg:text-[36px]">
          {vs.heading}
        </h2>
        <p className="mt-3 hidden text-[15px] leading-relaxed text-muted sm:block lg:text-[16px]">{vs.intro}</p>
      </div>

      <StepTabs
        steps={steps}
        active={step}
        onSelect={select}
        idPrefix="story"
        panelId="story-panel"
        label={vs.stepsLabel}
        className="[grid-area:steps] lg:self-start"
        progress={progress}
      />

      {/* Real evidence, stated plainly */}
      <p className="flex gap-2 text-[12px] leading-snug text-muted [grid-area:evidence] sm:text-[14px] lg:self-start">
        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="mt-px shrink-0 text-ok">
          <path d="M4 19V5M4 19h16M8 15l3-3 3 2 5-6" />
        </svg>
        <span>{vs.evidence}</span>
      </p>

      {/* Card */}
      <div className="relative mx-auto w-full max-w-[560px] [grid-area:card] lg:mx-0 lg:max-w-none">
        <div aria-hidden="true" className="demo-dots pointer-events-none absolute -inset-x-10 -inset-y-8" />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-12 -top-16 h-[380px] w-[380px] rounded-full opacity-60 blur-3xl [background:radial-gradient(circle_at_40%_60%,rgb(30_122_70/0.45),transparent_60%),radial-gradient(circle_at_70%_30%,rgb(252_74_26/0.45),transparent_60%)] sm:h-[460px] sm:w-[460px]"
        />
        <div
          {...touchProps}
          className="relative flex h-[min(540px,calc(100svh_-_362px))] flex-col overflow-hidden rounded-2xl border border-line bg-white shadow-[0_1px_2px_rgb(12_30_52/0.06),0_12px_24px_-12px_rgb(12_30_52/0.18),0_40px_70px_-30px_rgb(12_30_52/0.35)] sm:h-[min(540px,calc(100svh_-_300px))] lg:h-[min(540px,calc(100svh_-_200px))]"
        >
          <span aria-hidden="true" className="h-1 shrink-0 bg-[linear-gradient(90deg,var(--color-orange-strong),var(--color-orange)_60%,#ff9a7a)]" />
          <div
            id="story-panel"
            role="tabpanel"
            tabIndex={0}
            aria-labelledby={`story-tab-${step}`}
            aria-live="polite"
            className="chat-scroll relative flex min-h-0 flex-1 flex-col overflow-y-auto focus-visible:outline-offset-[-3px]"
          >
            {[ChallengeCard, DidCard, OutcomeCard].map((Card, i) => (
              <div
                key={i === step ? `on-${runKey}` : `off-${i}`}
                hidden={i !== step}
                className={cn("flex flex-1 flex-col", i === step && animate && "bx-card-in bx-run")}
              >
                <Card />
              </div>
            ))}
          </div>
          {/* Always visible: this is an illustration, not a record */}
          <p className="flex shrink-0 gap-2 border-t border-line bg-cream/80 px-5 py-2.5 text-[12.5px] leading-snug text-muted sm:px-7">
            <svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="mt-px shrink-0">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 11v5M12 7.5v.01" />
            </svg>
            <span>{vs.note}</span>
          </p>
        </div>
      </div>
    </div>
  );
}

/* ---------- Cards ---------- */

const it = (i: number) => ({ style: { "--i": i } as CSSProperties });

function Header({ kicker, title, aside }: { kicker: string; title: ReactNode; aside?: ReactNode }) {
  return (
    <div className="bx-grid flex items-start gap-3 border-b border-line px-5 pb-2.5 pt-3 sm:px-7 sm:pb-3 sm:pt-5">
      {aside}
      <div className="min-w-0">
        <p className="text-[11.5px] font-bold uppercase tracking-[0.14em] text-muted">{kicker}</p>
        <h3 className="mt-1 font-display text-[16.5px] font-bold leading-tight text-navy-deep sm:text-[21px]">{title}</h3>
      </div>
    </div>
  );
}

function ChallengeCard() {
  const c = vs.challenge;
  return (
    <article aria-label={`${c.kicker}: ${c.farmer}`} className="flex flex-1 flex-col">
      <Header
        kicker={c.kicker}
        title={c.farmer}
        aside={
          <span aria-hidden="true" className="hidden h-12 w-12 shrink-0 place-items-center rounded-[12px] bg-[#fdf6e3] text-[#b7791f] sm:grid">
            <MaizeIcon />
          </span>
        }
      />
      <div className="flex-1 px-5 py-4 sm:px-7">
        <div {...it(0)} className="bx-item flex flex-wrap gap-2">
          <span className="rounded-full border border-line bg-cream px-3 py-1 text-[13.5px] font-semibold text-navy-deep">{c.location}</span>
          <span className="rounded-full border border-line bg-cream px-3 py-1 text-[13.5px] font-semibold text-navy-deep">{c.crop}</span>
        </div>
        <p {...it(1)} className="bx-item mt-1.5 text-[13px] text-muted">{c.cropDetail}</p>

        <h4 {...it(2)} className="bx-item mt-4 text-[12px] font-bold uppercase tracking-[0.12em] text-muted">{c.problemsTitle}</h4>
        <ul className="mt-2 space-y-2">
          {c.problems.map((p, i) => (
            <li key={p} {...it(3 + i)} className="bx-item flex gap-2.5 text-[14.5px] leading-snug">
              <span className="mt-0.5 text-warn"><WarnGlyph /></span>
              <span>{p}</span>
            </li>
          ))}
        </ul>

        <p {...it(7)} className="bx-item mt-4 inline-flex items-center gap-2 rounded-[10px] border border-dashed border-warn bg-warn-wash px-3 py-1.5 text-[14px] font-semibold text-warn">
          {c.brokerTag}
          <span aria-hidden="true" className="grid h-5 w-5 place-items-center rounded-full bg-warn text-[12px] font-bold text-white">?</span>
          <span className="sr-only">(is this fair?)</span>
        </p>
      </div>
    </article>
  );
}

function DidCard() {
  const d = vs.did;
  return (
    <article aria-label={`${d.kicker}: ${d.title}`} className="flex flex-1 flex-col">
      <Header kicker={d.kicker} title={d.title} />
      <ol className="flex-1 divide-y divide-line px-5 sm:px-7">
        {d.actions.map((a, i) => (
          <li key={a.title} {...it(i)} className="bx-item flex gap-3 py-3" style={{ "--i": i, "--d": `${450 + i * 420}ms` } as CSSProperties}>
            <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-[10px] bg-orange-wash text-orange-ink">
              <ActionIcon name={a.icon} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[15px] font-bold text-navy-deep">{a.title}</p>
                {/* Status: a spinner that "completes" into a drawn check mark */}
                <span className="relative grid h-6 w-6 shrink-0 place-items-center">
                  <span aria-hidden="true" className="bx-skel absolute inset-0 grid place-items-center">
                    <span className="bx-spin h-4 w-4 rounded-full border-2 border-line border-t-orange-strong" />
                  </span>
                  <span className="bx-chip grid h-6 w-6 place-items-center rounded-full bg-ok-wash text-ok">
                    <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                      <path className="bx-draw" d="M5 12.5l4.5 4.5L19 7.5" />
                    </svg>
                    <span className="sr-only">Done</span>
                  </span>
                </span>
              </div>
              <p className="mt-0.5 text-[13.5px] leading-snug text-muted">{a.body}</p>
              {a.chip && (
                <span className="bx-chip mt-1.5 inline-flex items-center gap-1.5 rounded-full bg-warn-wash px-2.5 py-0.5 text-[12.5px] font-semibold text-warn" style={{ animationDelay: `calc(var(--d) + 250ms)` }}>
                  <WarnGlyph />
                  {a.chip}
                </span>
              )}
            </div>
          </li>
        ))}
      </ol>
    </article>
  );
}

function OutcomeCard() {
  const o = vs.outcome;
  const max = Math.max(...o.bars.map((b) => b.value));
  return (
    <article aria-label={`${o.kicker}: ${o.title}`} className="flex flex-1 flex-col">
      <Header kicker={o.kicker} title={o.title} />
      <div className="flex-1 px-5 py-4 sm:px-7">
        <h4 {...it(0)} className="bx-item text-[12px] font-bold uppercase tracking-[0.12em] text-muted">{o.compareTitle}</h4>
        <dl className="mt-2.5 space-y-2.5">
          {o.bars.map((b, i) => {
            const better = b.value === max;
            return (
              <div key={b.label} {...it(1 + i)} className="bx-item">
                <dt className="flex justify-between text-[13.5px]">
                  <span className={better ? "font-semibold text-navy-deep" : "text-muted"}>{b.label}</span>
                </dt>
                <dd className="mt-1 flex items-center gap-3">
                  <span className="h-3.5 flex-1 overflow-hidden rounded-full bg-[#f0ece2]">
                    <span
                      className={cn("bx-bar block h-full rounded-full", better ? "bg-ok" : "bg-[#b9b2a3]")}
                      style={{ width: `${(b.value / max) * 100}%`, animationDelay: `${300 + i * 250}ms` }}
                    />
                  </span>
                  <span className={cn("w-[84px] shrink-0 text-right text-[15px] font-bold tabular-nums", better ? "text-ok" : "text-muted")}>{b.display}</span>
                </dd>
              </div>
            );
          })}
        </dl>

        <ul className="mt-4 space-y-2.5">
          {o.notes.map((n, i) => (
            <li key={n.label} {...it(4 + i)} className="bx-item flex gap-2.5 text-[14px] leading-snug">
              <span className="mt-0.5 text-warn"><WarnGlyph /></span>
              <span>
                <strong className="font-semibold text-warn">{n.label}: </strong>
                {n.text}
              </span>
            </li>
          ))}
        </ul>

        <p {...it(7)} className="bx-item mt-4 flex gap-2.5 rounded-[10px] bg-ok-wash px-3 py-2 text-[14px] leading-snug text-ok" style={{ "--i": 7, "--d": "1250ms" } as CSSProperties}>
          <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 shrink-0">
            <path className="bx-draw" d="M5 12.5l4.5 4.5L19 7.5" />
          </svg>
          <span>
            <strong className="font-bold">{o.recorded}</strong>
            <span className="block text-[13px] text-ok/90">{o.recordedBody}</span>
          </span>
        </p>
      </div>
    </article>
  );
}

/* ---------- Icons ---------- */

function MaizeIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 4c3.2 2 4.6 6 4.6 10.4S19.2 23.6 16 26c-3.2-2.4-4.6-7.2-4.6-11.6S12.8 6 16 4z" fill="#f6d365" />
      <path d="M16 6.5v17M13 10.5h6M12.3 14.5h7.4M12.7 18.5h6.6" stroke="#b7791f" strokeWidth="1.3" />
      <path d="M11.4 13C8 14.5 6.5 18.5 7 23c3.6.4 6.4-1 8.2-3.4" fill="#8bc34a" stroke="#4b7f2a" />
      <path d="M20.6 13c3.4 1.5 4.9 5.5 4.4 10-3.6.4-6.4-1-8.2-3.4" fill="#8bc34a" stroke="#4b7f2a" />
      <path d="M16 26v2.5" stroke="#4b7f2a" />
    </svg>
  );
}

function ActionIcon({ name }: { name: "price" | "shield" | "list" | "link" }) {
  const common = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  if (name === "price")
    return (
      <svg {...common}>
        <path d="M3 12V4h8l10 10-8 8z" />
        <circle cx="7.5" cy="8.5" r="1.5" fill="currentColor" />
      </svg>
    );
  if (name === "shield")
    return (
      <svg {...common}>
        <path d="M12 3l7 3v6c0 4.4-3 7.8-7 9-4-1.2-7-4.6-7-9V6l7-3z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
    );
  if (name === "list")
    return (
      <svg {...common}>
        <path d="M9 6h11M9 12h11M9 18h11" />
        <path d="M4 6l1 1 1.5-2M4 12l1 1 1.5-2M4 18l1 1 1.5-2" />
      </svg>
    );
  return (
    <svg {...common}>
      <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" />
      <path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />
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
