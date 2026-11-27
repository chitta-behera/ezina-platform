"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { MenuIcon } from "./icons";

/**
 * Mobile navigation built on native <details>, so it works without JavaScript.
 * The small script only closes it after a link is chosen or Escape is pressed.
 */
export function MobileMenu({ label, children }: { label: string; children: ReactNode }) {
  const ref = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && ref.current?.open) {
        ref.current.open = false;
        ref.current.querySelector("summary")?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <details ref={ref} className="group lg:hidden">
      <summary
        className="grid h-11 w-11 list-none place-items-center rounded-[10px] border border-line text-navy"
        aria-label={label}
      >
        <MenuIcon />
      </summary>
      <div
        className="absolute inset-x-0 top-full border-b border-line bg-cream shadow-lg"
        onClick={(e) => {
          if ((e.target as HTMLElement).closest("a") && ref.current) ref.current.open = false;
        }}
      >
        {children}
      </div>
    </details>
  );
}
