"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { cn } from "@ezina/ui";

/**
 * On-scroll entrance for a group of items: children with the `reveal-item` class (and a `--i` index) fade and rise
 * one after another (~80 ms apart) when the group scrolls into view.
 * Content is never hidden without JavaScript, under prefers-reduced-motion, or when the group is already on screen
 * at load: items are only "armed" (hidden) just before they animate, and only if they are still below the fold.
 */
export function Reveal({ as: Tag = "div", className, children }: { as?: "div" | "ul" | "ol"; className?: string; children: ReactNode }) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || !("IntersectionObserver" in window)) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (el.getBoundingClientRect().top < window.innerHeight * 0.9) return; // already visible: leave it static
    el.classList.add("reveal-armed");
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;
        el.classList.add("reveal-in");
        io.disconnect();
      },
      { threshold: 0.15 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    <Tag ref={ref as any} className={cn(className)}>
      {children}
    </Tag>
  );
}
