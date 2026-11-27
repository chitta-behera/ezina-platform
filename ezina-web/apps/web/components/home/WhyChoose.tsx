import type { CSSProperties } from "react";
import { whyChoose } from "@/content/site";
import { Reveal } from "../Reveal";
import { SectionHeading } from "../SectionHeading";
import { whyIcons } from "../icons";

/**
 * "Why choose Ezina?": five compact items. 1 column on phones, 2 from sm, 3 + 2 centred from lg, 5 in a row from xl.
 * Items rise in one after another on scroll (Reveal); cards lift on hover (desktop).
 */
export function WhyChoose() {
  return (
    <section aria-labelledby="why-heading" className="py-8 sm:py-16">
      <div className="container-page">
        <SectionHeading id="why-heading" eyebrow={whyChoose.eyebrow} heading={whyChoose.heading} intro={whyChoose.intro} />
        <Reveal as="ul" className="mt-5 grid gap-2.5 sm:mt-8 sm:grid-cols-2 sm:gap-4 lg:grid-cols-6 xl:grid-cols-5">
          {whyChoose.items.map((item, i) => {
            const Icon = whyIcons[item.icon];
            return (
              <li
                key={item.title}
                style={{ "--i": i } as CSSProperties}
                className={[
                  "reveal-item group flex rounded-2xl border border-line bg-white px-4 py-3 shadow-[0_8px_24px_-20px_rgb(12_30_52/0.5)] sm:p-5",
                  "transition-[transform,box-shadow] duration-300 ease-out hover:-translate-y-1 hover:shadow-[0_18px_36px_-18px_rgb(12_30_52/0.4)]",
                  "lg:col-span-2 xl:col-span-1",
                  i === 3 ? "lg:col-start-2 xl:col-start-auto" : "",
                ].join(" ")}
              >
                <div className="flex items-start gap-4 sm:block">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full sm:h-11 sm:w-11 bg-orange-wash text-orange-ink transition-colors duration-300 group-hover:bg-[#ffe1d4]">
                    <Icon size={22} />
                  </span>
                  <div>
                    <h3 className="font-display text-[16.5px] font-bold leading-snug text-navy-deep sm:mt-4 sm:text-[17px]">{item.title}</h3>
                    <p className="mt-0.5 text-[14px] leading-snug text-muted sm:mt-1.5 sm:text-[15px]">{item.body}</p>
                  </div>
                </div>
              </li>
            );
          })}
        </Reveal>
      </div>
    </section>
  );
}
