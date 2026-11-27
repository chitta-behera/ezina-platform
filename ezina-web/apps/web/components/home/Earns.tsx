import type { CSSProperties } from "react";
import { cn } from "@ezina/ui";
import { earns } from "@/content/site";
import { PlanHighlighter } from "../PlanHighlighter";
import { Reveal } from "../Reveal";
import { SectionHeading } from "../SectionHeading";
import { ChatIcon, CheckIcon, NoCutIcon } from "../icons";

/**
 * "How Ezina earns" (#pricing): pricing-style cards with no prices and no Get Started.
 * Equal-height cards with CTAs aligned at the bottom; the Buyers card is emphasised; the Farmers card has a Free badge.
 */
export function Earns() {
  return (
    <section id={earns.id} aria-labelledby="earns-heading" className="border-y border-line bg-paper py-14 sm:py-20">
      <div className="container-page">
        <SectionHeading id="earns-heading" eyebrow={earns.eyebrow} heading={earns.heading} intro={earns.intro} />

        <Reveal as="ul" className="mt-10 grid gap-5 lg:grid-cols-3 lg:items-stretch">
          {earns.cards.map((card, i) => {
            const emphasised = !!card.highlight;
            return (
              <li key={card.id} id={card.id} style={{ "--i": i } as CSSProperties} className="reveal-item plan-card relative flex">
                <article
                  aria-labelledby={`${card.id}-title`}
                  className={cn(
                    "relative flex w-full flex-col overflow-hidden rounded-2xl bg-white shadow-[0_1px_2px_rgb(12_30_52/0.05),0_16px_36px_-24px_rgb(12_30_52/0.45)]",
                    emphasised ? "border-2 border-orange-strong" : "border-2 border-line",
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cn("h-1.5 shrink-0", emphasised ? "bg-orange-strong" : "bg-[linear-gradient(90deg,var(--color-orange-strong),#ff9a7a)] opacity-70")}
                  />
                  <div className="flex flex-1 flex-col p-6 sm:p-7">
                    <div className="flex min-h-7 items-center justify-between gap-3">
                      <p className="text-[12.5px] font-bold uppercase tracking-[0.14em] text-orange-ink">{card.audience}</p>
                      {card.highlight && (
                        <span className="rounded-full bg-orange-strong px-2.5 py-1 text-[11.5px] font-bold uppercase tracking-[0.08em] text-white">
                          {card.highlight}
                        </span>
                      )}
                      {card.badge && (
                        <span className="rounded-full bg-ok-wash px-2.5 py-1 text-[11.5px] font-bold uppercase tracking-[0.08em] text-ok">
                          {card.badge}
                        </span>
                      )}
                    </div>
                    <h3 id={`${card.id}-title`} className="mt-2 font-display text-[22px] font-bold leading-tight text-navy-deep">
                      {card.title}
                    </h3>
                    <ul className="mt-5 flex-1 space-y-3">
                      {card.items.map((item) => (
                        <li key={item} className="flex gap-2.5 text-[15.5px] leading-snug">
                          <CheckIcon size={18} strokeWidth={2.6} className="mt-[3px] shrink-0 text-orange" />
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                    <a
                      href={card.cta.href}
                      {...(card.cta.external ? { rel: "noopener" } : {})}
                      className={cn(
                        "mt-7 inline-flex items-center justify-center rounded-[var(--radius-btn)] border-2 px-5 py-2.5 text-[15.5px] font-semibold no-underline transition-colors",
                        emphasised
                          ? "border-orange-strong bg-orange-strong text-white hover:border-orange-stronger hover:bg-orange-stronger"
                          : "border-navy/25 text-navy hover:border-navy",
                      )}
                    >
                      {card.cta.label}
                    </a>
                  </div>
                </article>
              </li>
            );
          })}
        </Reveal>
        <PlanHighlighter />

        <Reveal as="ul" className="mt-6 grid gap-3 md:grid-cols-2">
          {earns.statements.map((s, i) => (
            <li
              key={s.text}
              style={{ "--i": i + 3 } as CSSProperties}
              className="reveal-item flex items-center gap-3 rounded-[14px] border border-line bg-cream px-5 py-4 text-[15.5px] font-semibold text-navy-deep"
            >
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-white text-orange-ink shadow-sm">
                {s.icon === "nocut" ? <NoCutIcon size={20} /> : <ChatIcon size={20} />}
              </span>
              <span>{s.text}</span>
            </li>
          ))}
        </Reveal>
      </div>
    </section>
  );
}
