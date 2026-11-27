"use client";

import { useRef, type KeyboardEvent } from "react";
import { cn } from "@ezina/ui";

export type StepTabItem = { title: string; body: string };

type Props = {
  steps: readonly StepTabItem[];
  /** Index of the active step, or null when none is active yet (e.g. the static full view). */
  active: number | null;
  onSelect: (i: number) => void;
  /** Prefix for tab ids: tabs are `${idPrefix}-tab-${i}`. */
  idPrefix: string;
  /** id of the tabpanel the tabs control. */
  panelId: string;
  label: string;
  className?: string;
  /**
   * Optional progress bar on the active tab. It is a CSS animation (scaleX 0→1) that drives auto-advance:
   * `onDone` fires when it finishes; `paused` freezes it. Not rendered when null (e.g. reduced motion).
   */
  progress?: { runKey: string | number; durationMs: number; paused: boolean; onDone: () => void } | null;
};

/**
 * Shared step tabs for the stepper sections (WhatsApp demo, What buyers receive).
 * Phones: numbered dots plus the active step's title. From sm: 4/3 tabs in a row. From lg: a compact vertical list
 * with an accent bar and one-line descriptions. Keyboard: arrow keys, Home and End (roving tabindex).
 */
export function StepTabs({ steps, active, onSelect, idPrefix, panelId, label, className, progress }: Props) {
  const tabs = useRef<Array<HTMLButtonElement | null>>([]);
  const last = steps.length - 1;
  const current = active ?? 0;

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const keys: Record<string, number> = {
      ArrowRight: current + 1,
      ArrowDown: current + 1,
      ArrowLeft: current - 1,
      ArrowUp: current - 1,
      Home: 0,
      End: last,
    };
    if (!(e.key in keys)) return;
    e.preventDefault();
    const next = (keys[e.key]! + steps.length) % steps.length;
    onSelect(next);
    tabs.current[next]?.focus();
  };

  return (
    <div
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
      className={cn(
        "flex items-center justify-center gap-1.5 sm:grid sm:gap-2.5 lg:grid-cols-1 lg:gap-2",
        steps.length === 4 ? "sm:grid-cols-4" : "sm:grid-cols-3",
        className,
      )}
    >
      {steps.map((s, i) => {
        const on = active === i;
        return (
          <button
            key={s.title}
            ref={(el) => {
              tabs.current[i] = el;
            }}
            id={`${idPrefix}-tab-${i}`}
            type="button"
            role="tab"
            aria-selected={on}
            aria-controls={panelId}
            tabIndex={i === current ? 0 : -1}
            onClick={() => onSelect(i)}
            className={cn(
              "relative flex min-h-11 items-center gap-2 overflow-hidden rounded-full border text-left transition-colors duration-300",
              "sm:rounded-[12px] sm:px-3 sm:py-2.5 lg:items-start lg:gap-3 lg:px-4 lg:py-3",
              on
                ? "border-line bg-white px-1.5 pr-3.5 shadow-[0_10px_26px_-16px_rgb(12_30_52/0.35)]"
                : "border-transparent px-1.5 hover:border-line hover:bg-white/60",
            )}
          >
            <span
              aria-hidden="true"
              className={cn(
                "absolute inset-x-0 top-0 hidden h-[3px] transition-colors duration-300 sm:block lg:inset-y-0 lg:left-0 lg:right-auto lg:h-auto lg:w-[3px]",
                on ? "bg-orange-strong" : "bg-line",
              )}
            />
            <span
              className={cn(
                "grid h-8 w-8 shrink-0 place-items-center rounded-full text-[13px] font-bold transition-colors duration-300 sm:h-6 sm:w-6 sm:text-[12px] lg:h-7 lg:w-7",
                on ? "bg-navy-deep text-white" : "bg-line text-navy",
              )}
            >
              {i + 1}
            </span>
            <span className={cn("min-w-0", on ? "block" : "sr-only sm:not-sr-only sm:block")}>
              <span
                className={cn(
                  "block font-display text-[13px] leading-snug text-navy-deep lg:text-[16px]",
                  on ? "font-bold" : "font-semibold",
                )}
              >
                {s.title}
              </span>
              <span className="mt-0.5 hidden truncate text-[14px] leading-snug text-muted lg:block">{s.body}</span>
            </span>

            {/* Auto-advance progress (time until the next step) */}
            {on && progress && (
              <span aria-hidden="true" className="absolute inset-x-3 bottom-0 block h-[2px] overflow-hidden rounded-full bg-orange-wash sm:inset-x-0 sm:rounded-none">
                <span
                  key={progress.runKey}
                  className="step-progress block h-full origin-left bg-orange-strong"
                  style={{ animationDuration: `${progress.durationMs}ms`, animationPlayState: progress.paused ? "paused" : "running" }}
                  onAnimationEnd={progress.onDone}
                />
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
