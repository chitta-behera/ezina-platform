"use client";

import { useEffect } from "react";

/**
 * Highlights a "How Ezina earns" card after a link with `data-highlight="<card id>"` is used
 * (e.g. "See how it works for institutions" → /#pricing, data-highlight="institutions-plan").
 * The link itself is a normal anchor (works without JS; smooth scroll comes from CSS). This script only waits until
 * the target card is actually on screen, then adds a one-off ring: a soft pulse that fades over ~1.5 s, or a static
 * ring for 2 s under prefers-reduced-motion. Renders nothing.
 */
export function PlanHighlighter() {
  useEffect(() => {
    let io: IntersectionObserver | null = null;
    let timer: number | undefined;

    const flash = (el: HTMLElement) => {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const cls = reduce ? "plan-flash-static" : "plan-flash";
      el.classList.remove("plan-flash", "plan-flash-static");
      void el.offsetWidth; // restart the animation if it is clicked again
      el.classList.add(cls);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => el.classList.remove(cls), reduce ? 2000 : 1600);
    };

    const onClick = (e: MouseEvent) => {
      const link = (e.target as Element | null)?.closest<HTMLAnchorElement>("a[data-highlight]");
      const id = link?.dataset.highlight;
      const card = id ? document.getElementById(id) : null;
      if (!card) return;
      io?.disconnect();
      // Wait for the smooth scroll to bring the card (mostly) on screen; on phones that may need a little more scrolling.
      io = new IntersectionObserver(
        ([entry]) => {
          if (!entry?.isIntersecting) return;
          io?.disconnect();
          io = null;
          window.setTimeout(() => flash(card), 150);
        },
        { threshold: 0.6 },
      );
      // Observe after the jump has started, so a card that is visible before scrolling doesn't fire too early.
      window.setTimeout(() => io?.observe(card), 250);
    };

    document.addEventListener("click", onClick);
    return () => {
      document.removeEventListener("click", onClick);
      io?.disconnect();
      window.clearTimeout(timer);
    };
  }, []);

  return null;
}
