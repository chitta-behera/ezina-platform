import { legal, links, type LegalSection } from "@/content/site";
import { AlertIcon } from "./icons";

type Props = { title: string; sections: LegalSection[] };

export function LegalPage({ title, sections }: Props) {
  return (
    <article className="container-page max-w-3xl py-12 sm:py-16">
      <div
        role="note"
        className="flex gap-3 rounded-[12px] border-2 border-dashed border-warn bg-warn-wash p-4 text-[15.5px] font-semibold text-warn"
      >
        <AlertIcon size={22} className="shrink-0" />
        <p>{legal.draftNotice}</p>
      </div>

      <h1 className="mt-8 font-display text-4xl font-bold tracking-[-0.02em] text-navy-deep">{title}</h1>
      <p className="mt-2 text-[15px] text-muted">Last updated: {legal.lastUpdated}</p>

      <div className="mt-8 space-y-8">
        {sections.map((s, i) => (
          <section key={s.heading} aria-labelledby={`legal-${i}`}>
            <h2 id={`legal-${i}`} className="font-display text-xl font-bold text-navy-deep">
              {i + 1}. {s.heading}
            </h2>
            {s.paragraphs?.map((p) => (
              <p key={p} className="mt-3">
                {p}
              </p>
            ))}
            {s.items && (
              <ul className="mt-3 list-disc space-y-2 pl-6 marker:text-orange">
                {s.items.map((it) => (
                  <li key={it}>{it}</li>
                ))}
              </ul>
            )}
          </section>
        ))}

        <section aria-labelledby="legal-contact">
          <h2 id="legal-contact" className="font-display text-xl font-bold text-navy-deep">
            {sections.length + 1}. Contact
          </h2>
          <p className="mt-3">
            Email{" "}
            <a href={`mailto:${links.email}`} className="font-semibold underline">
              {links.email}
            </a>
            . Operator: {legal.entityName}, {legal.address}.
          </p>
        </section>
      </div>
    </article>
  );
}
