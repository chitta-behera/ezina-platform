"use client";

import { useEffect, useRef } from "react";

/**
 * Shows `display` (e.g. "1K+") in the static HTML. With JavaScript, and unless the visitor prefers reduced motion,
 * it counts from 0 to `countTo` when scrolled into view, then settles on `display`.
 * Screen readers always get the final value; the animated digits are aria-hidden.
 */
export function CountUp({ display, countTo, duration = 1400 }: { display: string; countTo: number | null; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || countTo === null || countTo <= 0) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) return;

    let frame = 0;
    const fmt = new Intl.NumberFormat("en");
    const run = () => {
      const start = performance.now();
      const tick = (now: number) => {
        const p = Math.min(1, (now - start) / duration);
        const eased = 1 - Math.pow(1 - p, 3);
        el.textContent = p < 1 ? fmt.format(Math.round(eased * countTo)) : display;
        if (p < 1) frame = requestAnimationFrame(tick);
      };
      frame = requestAnimationFrame(tick);
    };

    el.textContent = "0";
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          io.disconnect();
          run();
        }
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(frame);
      el.textContent = display;
    };
  }, [countTo, display, duration]);

  return (
    <>
      <span className="sr-only">{display}</span>
      <span ref={ref} aria-hidden="true">
        {display}
      </span>
    </>
  );
}
