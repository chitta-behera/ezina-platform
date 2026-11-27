"use client";

import { useEffect, useRef, useState, type FocusEvent, type TouchEvent } from "react";

type Options = {
  /** Number of steps. */
  count: number;
  /** Time each step stays before auto-advancing (drives the progress bar). */
  durationMs: number;
  /**
   * `html` data attribute (camelCase dataset key) set while this section fills the screen, used by CSS to hide the
   * floating mobile WhatsApp shortcut so it never covers the step tabs. e.g. "buyersInView" → html[data-buyers-in-view].
   */
  fabKey: string;
};

/**
 * Shared behaviour for the card steppers ("What buyers receive", "Validation story"):
 * - starts when ~35% of the section is on screen (only without prefers-reduced-motion);
 * - auto-advance is driven by the active tab's CSS progress bar (StepTabs `progress`), so it pauses exactly with the
 *   bar: on hover, keyboard focus inside, or when the section is off-screen;
 * - click/tap (select), swipe left/right on the card (touchProps);
 * - reduced motion / no JS: no auto-advance, no item animation (`animate` stays false; cards show final states).
 */
export function useStepper({ count, durationMs, fabKey }: Options) {
  const [step, setStep] = useState(0);
  const [runKey, setRunKey] = useState(0);
  const [motion, setMotion] = useState(false);
  const [inView, setInView] = useState(false);
  const [hover, setHover] = useState(false);
  const [focusWithin, setFocusWithin] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const touchX = useRef<number | null>(null);

  useEffect(() => {
    const el = root.current;
    if (!el || !("IntersectionObserver" in window)) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let started = false;
    const io = new IntersectionObserver(
      ([entry]) => {
        const on = !!entry?.isIntersecting;
        setInView(on);
        if (on && !started && !reduce) {
          started = true;
          setMotion(true);
          setRunKey((k) => k + 1);
        }
      },
      { threshold: 0.35 },
    );
    io.observe(el);

    const html = document.documentElement;
    const fab = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) html.dataset[fabKey] = "";
        else delete html.dataset[fabKey];
      },
      { threshold: 0.6 },
    );
    fab.observe(el);
    return () => {
      io.disconnect();
      fab.disconnect();
      delete html.dataset[fabKey];
    };
  }, [fabKey]);

  const select = (i: number) => {
    setStep(i);
    setRunKey((k) => k + 1);
  };

  const progress = motion
    ? { runKey, durationMs, paused: hover || focusWithin || !inView, onDone: () => select((step + 1) % count) }
    : null;

  const containerProps = {
    ref: root,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    onFocus: () => setFocusWithin(true),
    onBlur: (e: FocusEvent<HTMLDivElement>) => {
      if (!root.current?.contains(e.relatedTarget as Node | null)) setFocusWithin(false);
    },
  };

  const touchProps = {
    onTouchStart: (e: TouchEvent) => {
      touchX.current = e.touches[0]?.clientX ?? null;
    },
    onTouchEnd: (e: TouchEvent) => {
      const start = touchX.current;
      touchX.current = null;
      if (start === null) return;
      const dx = (e.changedTouches[0]?.clientX ?? start) - start;
      if (Math.abs(dx) < 45) return;
      select(dx < 0 ? Math.min(count - 1, step + 1) : Math.max(0, step - 1));
    },
  };

  /** True once the stepper is animating (motion allowed and started): use it to add the `.bx-run` class. */
  const animate = motion;

  return { step, select, runKey, animate, progress, containerProps, touchProps };
}
