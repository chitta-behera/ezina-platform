import { audiences } from "@/content/site";
import { SectionHeading } from "../SectionHeading";
import { CheckIcon, audienceIcons } from "../icons";

/**
 * "What is Ezina for?": four equal-height audience cards (farmers, buyers, institutions, export partners).
 * 1 column on phones, 2×2 from md, 4 in a row from xl (1280px). No Get Started here: each card has a text link.
 */
export function Audiences() {
  return (
    <section aria-labelledby="audiences-heading" className="py-16 sm:py-20">
      <div className="container-page">
        <SectionHeading id="audiences-heading" eyebrow={audiences.eyebrow} heading={audiences.heading} />

        <ul className="mt-10 grid gap-5 md:auto-rows-fr md:grid-cols-2 xl:grid-cols-4">
          {audiences.cards.map((card) => {
            const Icon = audienceIcons[card.icon];
            const external = "external" in card.cta && card.cta.external;
            return (
              <li key={card.id} className="flex">
                <article
                  id={card.id}
                  aria-labelledby={`${card.id}-title`}
                  className="flex w-full flex-col rounded-[16px] border border-line bg-paper p-6 shadow-[0_10px_30px_-24px_rgb(12_30_52/0.5)] transition-shadow duration-300 hover:shadow-[0_18px_40px_-24px_rgb(12_30_52/0.45)] sm:p-7"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="grid h-12 w-12 shrink-0 place-items-center rounded-[12px] bg-orange-wash text-orange-ink">
                      <Icon size={24} />
                    </span>
                    {"badge" in card && card.badge && (
                      <span className="rounded-full bg-ok-wash px-2.5 py-1 text-[12px] font-bold uppercase tracking-[0.08em] text-ok">
                        {card.badge}
                      </span>
                    )}
                  </div>
                  <h3 id={`${card.id}-title`} className="mt-5 font-display text-[22px] font-bold leading-tight text-navy-deep">
                    {card.title}
                  </h3>
                  <ul className="mt-4 flex-1 space-y-2.5">
                    {card.benefits.map((b) => (
                      <li key={b} className="flex gap-2.5 text-[16px] leading-snug">
                        <CheckIcon size={18} strokeWidth={2.6} className="mt-[3px] shrink-0 text-orange" />
                        <span>{b}</span>
                      </li>
                    ))}
                  </ul>
                  {"note" in card && card.note && <p className="mt-4 text-[14.5px] font-semibold text-ok">{card.note}</p>}
                  <a
                    href={card.cta.href}
                    {...(external ? { rel: "noopener" } : {})}
                    {...("highlight" in card.cta && card.cta.highlight ? { "data-highlight": card.cta.highlight } : {})}
                    className="mt-6 inline-block self-start text-[15.5px] font-semibold text-orange-ink underline decoration-2 underline-offset-4 hover:text-orange-stronger"
                  >
                    {card.cta.label}
                  </a>
                </article>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
