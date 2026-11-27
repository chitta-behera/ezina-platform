import { howItWorks } from "@/content/site";
import { SectionHeading } from "../SectionHeading";
import { stepIcons } from "../icons";

export function HowItWorks() {
  return (
    <section
      id="how-it-works"
      aria-labelledby="how-heading"
      className="border-y border-line bg-paper py-16 sm:py-20"
    >
      <div className="container-page">
        <SectionHeading
          id="how-heading"
          eyebrow={howItWorks.eyebrow}
          heading={howItWorks.heading}
          intro={howItWorks.intro}
        />
        <ol className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {howItWorks.steps.map((step, i) => {
            const Icon = stepIcons[step.icon];
            return (
              <li key={step.title} className="relative rounded-[14px] border border-line bg-cream p-6">
                <div className="flex items-center justify-between">
                  <span className="grid h-12 w-12 place-items-center rounded-xl bg-navy text-white">
                    <Icon size={24} />
                  </span>
                  <span aria-hidden="true" className="font-display text-4xl font-extrabold text-line">
                    {i + 1}
                  </span>
                </div>
                <h3 className="mt-5 font-display text-xl font-bold text-navy-deep">
                  <span className="sr-only">Step {i + 1}: </span>
                  {step.title}
                </h3>
                <p className="mt-2 text-[16px] text-muted">{step.body}</p>
                {i < howItWorks.steps.length - 1 && (
                  <span
                    aria-hidden="true"
                    className="absolute -right-4 top-1/2 hidden -translate-y-1/2 text-2xl text-orange lg:block"
                  >
                    →
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
