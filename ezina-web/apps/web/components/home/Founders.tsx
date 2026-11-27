import { founders, isTodo } from "@/content/site";
import { SectionHeading } from "../SectionHeading";

export function Founders() {
  return (
    <section id="about" aria-labelledby="founders-heading" className="border-y border-line bg-paper py-16 sm:py-20">
      <div className="container-page">
        <SectionHeading id="founders-heading" eyebrow={founders.eyebrow} heading={founders.heading} intro={founders.intro} />
        <ul className="mt-10 grid gap-6 md:grid-cols-3">
          {founders.people.map((p) => (
            <li key={p.name} className="flex flex-col rounded-[14px] border border-line bg-cream p-6">
              <picture>
                <source srcSet={`${p.photo}.webp`} type="image/webp" />
                <img
                  src={`${p.photo}.jpg`}
                  alt={`${p.name}, ${p.role}, Ezina`}
                  width={112}
                  height={112}
                  loading="lazy"
                  decoding="async"
                  className="h-28 w-28 rounded-full object-cover ring-4 ring-paper"
                />
              </picture>
              <h3 className="mt-4 font-display text-xl font-bold text-navy-deep">{p.name}</h3>
              <p className="text-[14px] font-bold uppercase tracking-[0.12em] text-orange-ink">{p.role}</p>
              <p className="mt-3 flex-1 text-[15.5px] text-muted">{p.bio}</p>
              <p className="mt-4 text-[15px] font-semibold">
                {isTodo(p.linkedin) ? (
                  <span className="text-muted">LinkedIn: {p.linkedin}</span>
                ) : (
                  <a href={p.linkedin} rel="noopener" className="text-navy underline">
                    {p.name} on LinkedIn
                  </a>
                )}
              </p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
