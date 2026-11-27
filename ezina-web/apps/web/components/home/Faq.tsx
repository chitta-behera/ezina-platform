import { faq, isTodo } from "@/content/site";
import { JsonLd } from "../JsonLd";
import { SectionHeading } from "../SectionHeading";
import { PlusIcon } from "../icons";

export function Faq() {
  const faqLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faq.items.map((item) => ({
      "@type": "Question",
      name: item.q,
      acceptedAnswer: {
        "@type": "Answer",
        // Placeholders are left out of structured data.
        text: item.a.filter((p) => !isTodo(p)).join(" "),
      },
    })),
  };

  return (
    <section id="faq" aria-labelledby="faq-heading" className="py-16 sm:py-20">
      <JsonLd data={faqLd} />
      <div className="container-page grid gap-10 lg:grid-cols-[0.8fr_1.2fr]">
        <SectionHeading id="faq-heading" eyebrow={faq.eyebrow} heading={faq.heading} />
        <div className="divide-y divide-line rounded-[14px] border border-line bg-paper">
          {faq.items.map((item) => (
            <details key={item.q} className="group px-5 sm:px-6">
              <summary className="flex list-none items-start justify-between gap-4 py-5 font-display text-[18px] font-bold text-navy-deep">
                <span>{item.q}</span>
                <PlusIcon size={22} className="mt-0.5 shrink-0 text-orange-ink transition-transform group-open:rotate-45" />
              </summary>
              <div className="space-y-3 pb-5 text-[16px] text-ink">
                {item.a.map((p) => (
                  <p key={p}>{p}</p>
                ))}
              </div>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
