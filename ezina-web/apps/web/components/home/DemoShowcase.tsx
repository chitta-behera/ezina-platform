"use client";

import { useEffect, useRef, useState, type TouchEvent } from "react";
import { cn } from "@ezina/ui";
import { demo, type ChatMessage, type DemoCard } from "@/content/site";
import { Bubble, PhoneFrame, TypingBubble } from "../ChatPhone";
import { StepTabs } from "../StepTabs";

const steps = demo.steps;
const LAST = steps.length - 1;
const ALL: ChatMessage[] = steps.flatMap((s) => s.messages);
const STEP_MS = 5000; // minimum time a step stays on screen during autoplay
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/**
 * One phone whose chat follows the active step, sized so the whole section fits one screen.
 * - Static HTML / no JS: the whole conversation (all steps) is in the chat, starting with the farmer's question.
 * - With motion: starts when scrolled into view; each step plays its own messages (typing dots before Ezina),
 *   auto-advances every ~5 s, pauses on hover or focus and while off-screen. The chat scrolls inside the phone only.
 * - Reduced motion: no autoplay; selecting a step shows its final state.
 */
export function DemoShowcase() {
  const uid = "demo";
  const [full, setFull] = useState(true); // whole conversation (before JS takes over)
  const [step, setStep] = useState(LAST);
  const [shown, setShown] = useState(steps[LAST]!.messages.length);
  const [typing, setTyping] = useState(false);
  const [faded, setFaded] = useState(false);
  const [btnHidden, setBtnHidden] = useState(false); // quick-reply buttons of the newest message not shown yet
  const [tapped, setTapped] = useState<string | null>(null); // quick-reply button showing a tap highlight

  const root = useRef<HTMLDivElement>(null);
  const chat = useRef<HTMLDivElement>(null);
  const goTo = useRef<(s: number) => void>(() => {});
  const motionRef = useRef(false);
  const paused = useRef(false);
  const touchX = useRef<number | null>(null);

  useEffect(() => {
    const motion = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    motionRef.current = motion;
    let run = 0;
    let inView = false;
    let started = false;

    const play = async (s: number) => {
      const id = ++run;
      const alive = () => id === run;
      const msgs = steps[s]!.messages;
      if (!motion) {
        setFull(false);
        setStep(s);
        setShown(msgs.length);
        setTyping(false);
        setBtnHidden(false);
        setTapped(null);
        return;
      }
      setFaded(true);
      await sleep(220);
      if (!alive()) return;
      setFull(false);
      setStep(s);
      setShown(0);
      setTyping(false);
      setBtnHidden(false);
      setTapped(null);
      setFaded(false);
      const t0 = performance.now();
      await sleep(380);
      for (let i = 0; i < msgs.length; i++) {
        if (!alive()) return;
        const m: ChatMessage = msgs[i]!;
        if (m.from === "ezina") {
          setTyping(true);
          await sleep(1100);
          if (!alive()) return;
          setTyping(false);
        }
        setTapped(null);
        if (m.buttons?.length) {
          // Question first, then its reply buttons, then a tap on the chosen one.
          setBtnHidden(true);
          setShown(i + 1);
          await sleep(600);
          if (!alive()) return;
          setBtnHidden(false);
          await sleep(1000);
          if (!alive()) return;
          if (m.tap) {
            setTapped(m.tap);
            await sleep(650);
          }
          continue;
        }
        setShown(i + 1);
        await sleep(650);
      }
      await sleep(Math.max(2400, STEP_MS - (performance.now() - t0)));
      while (alive() && (paused.current || !inView)) await sleep(250);
      if (alive()) void play(s === LAST ? 0 : s + 1);
    };

    goTo.current = (s) => void play(s);
    if (!root.current || !("IntersectionObserver" in window)) return;

    // While the demo fills the screen, hide the floating mobile WhatsApp shortcut (it would cover the step tabs).
    const html = document.documentElement;
    const hideFab = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) html.dataset.demoInView = "";
        else delete html.dataset.demoInView;
      },
      { threshold: 0.6 },
    );
    hideFab.observe(root.current);
    if (!motion) {
      return () => {
        hideFab.disconnect();
        delete html.dataset.demoInView;
      };
    }

    const io = new IntersectionObserver(
      ([entry]) => {
        inView = !!entry?.isIntersecting;
        if (inView && !started) {
          started = true;
          void play(0);
        }
      },
      { threshold: 0.35 },
    );
    io.observe(root.current);
    return () => {
      io.disconnect();
      hideFab.disconnect();
      delete html.dataset.demoInView;
      run++;
    };
  }, []);

  // New step: start its conversation at the top (scrolls the chat box only, never the page).
  useEffect(() => {
    if (chat.current) chat.current.scrollTop = 0;
  }, [step, full]);

  // While a step plays, keep the newest message in view with a smooth scroll of the chat box.
  useEffect(() => {
    const el = chat.current;
    if (!el || full || !motionRef.current || shown === 0) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [shown, typing, btnHidden, full]);

  const select = (s: number) => {
    if (full || s !== step || shown < steps[s]!.messages.length) goTo.current(s);
  };

  const onTouchEnd = (e: TouchEvent) => {
    const start = touchX.current;
    touchX.current = null;
    if (start === null) return;
    const dx = (e.changedTouches[0]?.clientX ?? start) - start;
    if (Math.abs(dx) < 45) return;
    select(dx < 0 ? Math.min(LAST, step + 1) : Math.max(0, step - 1));
  };

  const visible: ChatMessage[] = full ? ALL : steps[step]!.messages.slice(0, shown);
  const cardOn = (c: DemoCard) => full || c.fromStep < step || (c.fromStep === step && shown >= 1);

  return (
    <div
      ref={root}
      onMouseEnter={() => (paused.current = true)}
      onMouseLeave={() => (paused.current = false)}
      onFocus={() => (paused.current = true)}
      onBlur={() => (paused.current = false)}
      className="grid w-full items-center gap-x-16 gap-y-3 [grid-template-areas:'head'_'phone'_'steps'] sm:gap-y-6 lg:grid-cols-[0.95fr_1.05fr] lg:grid-rows-[auto_auto] lg:gap-y-7 lg:[grid-template-areas:'head_phone'_'steps_phone']"
    >
      {/* Heading (compact: the intro is hidden on very small phones so everything fits one screen) */}
      <div className="max-w-xl [grid-area:head] lg:self-end">
        <p className="mb-1.5 text-[12px] font-bold uppercase tracking-[0.16em] text-orange-ink sm:mb-2.5 sm:text-[13px]">{demo.eyebrow}</p>
        <h2
          id={`${uid}-heading`}
          className="font-display text-[24px] font-bold leading-[1.12] tracking-[-0.02em] text-navy-deep sm:text-[32px] lg:text-[38px]"
        >
          {demo.heading}
        </h2>
        <p className="mt-3 hidden text-[15px] leading-relaxed text-muted sm:block lg:text-[16.5px]">{demo.intro}</p>
      </div>

      {/* Steps (shared StepTabs): dots + active title on small phones, tabs from sm, a compact list from lg */}
      <StepTabs
        steps={steps}
        active={full ? null : step}
        onSelect={select}
        idPrefix={uid}
        panelId={`${uid}-chat`}
        label={demo.stepsLabel}
        className="[grid-area:steps] lg:self-start"
      />

      {/* Phone with backdrop and floating cards */}
      <div className="relative flex flex-col items-center [grid-area:phone]">
        <div aria-hidden="true" className="demo-dots pointer-events-none absolute -inset-x-16 -inset-y-6" />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute left-1/2 top-1/2 h-[380px] w-[380px] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-70 blur-3xl [background:radial-gradient(circle_at_35%_35%,rgb(252_74_26/0.55),transparent_60%),radial-gradient(circle_at_70%_70%,rgb(30_122_70/0.40),transparent_60%)] sm:h-[480px] sm:w-[480px]"
        />

        <div className="relative" onTouchStart={(e) => (touchX.current = e.touches[0]?.clientX ?? null)} onTouchEnd={onTouchEnd}>
          <PhoneFrame>
            <div
              ref={chat}
              id={`${uid}-chat`}
              role="tabpanel"
              tabIndex={0}
              aria-labelledby={full ? undefined : `${uid}-tab-${step}`}
              aria-label={full ? demo.label : undefined}
              className={cn(
                "chat-scroll absolute inset-0 overflow-y-auto overflow-x-hidden transition-opacity duration-200 focus-visible:outline-offset-[-3px]",
                faded && "opacity-0",
              )}
            >
              <ol aria-live="polite" aria-label={demo.label} className="flex flex-col px-2 pb-2 pt-2">
                {visible.map((m, i) => {
                  const prev = visible[i - 1];
                  const newest = i === visible.length - 1;
                  return (
                    <Bubble
                      key={`${full ? "all" : step}-${i}`}
                      m={m}
                      first={!prev || prev.from !== m.from}
                      hideButtons={newest && btnHidden}
                      tapped={newest ? tapped : null}
                      className={full ? undefined : "demo-pop"}
                    />
                  );
                })}
                {typing && <TypingBubble className="demo-pop" />}
              </ol>
            </div>
          </PhoneFrame>

          {/* Floating cards (tablet and desktop); positioned within the phone's height */}
          {demo.cards.map((c) => (
            <FloatingCard key={c.title} card={c} on={cardOn(c)} />
          ))}
        </div>

        <p className="relative mt-2 text-[12px] font-medium text-muted sm:mt-3 lg:mt-4 lg:text-[13px]">{demo.label}</p>
      </div>
    </div>
  );
}

const positions: Record<DemoCard["position"], string> = {
  "top-left": "-left-[176px] top-[13%]",
  "top-right": "-right-[176px] top-[27%]",
  "mid-right": "-right-[176px] top-[52%]",
  "bottom-left": "-left-[176px] bottom-[12%]",
};

function FloatingCard({ card, on }: { card: DemoCard; on: boolean }) {
  const icon =
    card.icon === "check" ? (
      <span className="grid h-7 w-7 place-items-center rounded-full bg-ok-wash text-ok">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5 12.5l4.5 4.5L19 7.5" />
        </svg>
      </span>
    ) : card.icon === "price" ? (
      <span className="grid h-7 w-7 place-items-center rounded-full bg-orange-wash text-orange-ink">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round">
          <path d="M3 12V4h8l10 10-8 8z" />
          <circle cx="7.5" cy="8.5" r="1.5" fill="currentColor" />
        </svg>
      </span>
    ) : card.icon === "search" ? (
      <span className="grid h-7 w-7 place-items-center rounded-full bg-[#e3f1fb] text-[#1565c0]">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
          <circle cx="10.5" cy="10.5" r="6.5" />
          <path d="M15.5 15.5L21 21" />
        </svg>
      </span>
    ) : (
      <span className="grid h-7 w-7 place-items-center rounded-full bg-warn-wash text-warn">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 3.5L2.5 20h19z" />
          <path d="M12 10v4.5M12 17.5v.01" />
        </svg>
      </span>
    );

  return (
    <div
      aria-hidden={!on}
      className={cn(
        "absolute z-10 hidden w-[196px] transition-[opacity,transform] duration-500 ease-out md:block",
        positions[card.position],
        on ? "translate-y-0 opacity-100" : "pointer-events-none translate-y-3 opacity-0",
      )}
    >
      <div
        className={cn(
          "demo-float flex items-start gap-2.5 rounded-[12px] border border-white/70 bg-white/90 p-2.5 shadow-[0_16px_36px_-16px_rgb(12_30_52/0.4)] backdrop-blur-md",
          card.position === "mid-right" && "[animation-delay:-2s]",
          card.position === "bottom-left" && "[animation-delay:-4s]",
          card.position === "top-right" && "[animation-delay:-1s]",
        )}
      >
        <span className="shrink-0">{icon}</span>
        <span className="min-w-0">
          <span className="block text-[13px] font-bold leading-tight text-navy-deep">{card.title}</span>
          <span className="mt-0.5 block text-[12px] leading-snug text-muted">{card.body}</span>
        </span>
      </div>
    </div>
  );
}
