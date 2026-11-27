import { hero, links, stats, statsHeading } from "@/content/site";
import { CountUp } from "../CountUp";
import { GetStarted } from "../GetStarted";
import { stepIcons } from "../icons";

/**
 * Full-bleed photo hero: a cornfield at sunset under a deep green overlay, copy and stats on the left,
 * frosted-glass feature cards on the right (stacked under the copy on phones).
 * The photo is a plain <picture> (tall crop for phones, wide crops for larger screens); all text is in the HTML.
 */
export function Hero() {
  const { photo } = hero;
  return (
    <section aria-labelledby="hero-heading" className="relative isolate overflow-hidden bg-[#0d2a1d] text-white">
      {/* Photo */}
      <picture>
        <source media="(max-width: 767px)" srcSet={photo.mobile} />
        <source media="(min-width: 768px)" srcSet={`${photo.wide} 1280w, ${photo.wide2x} 1920w`} sizes="100vw" />
        <img
          src={photo.wide}
          alt={photo.alt}
          width={1280}
          height={720}
          fetchPriority="high"
          decoding="async"
          className="absolute inset-0 -z-20 h-full w-full object-cover object-[50%_30%]"
        />
      </picture>
      {/* Green overlay: darkest behind the copy, lighter on the right so the sunset shows */}
      <div
        aria-hidden="true"
        className="absolute inset-0 -z-10 bg-[linear-gradient(180deg,rgb(8_30_20/0.38)_0%,rgb(8_30_20/0.62)_45%,rgb(6_22_15/0.9)_100%)] md:bg-[linear-gradient(90deg,rgb(7_28_19/0.86)_0%,rgb(9_34_23/0.6)_40%,rgb(9_34_23/0.12)_75%,rgb(9_34_23/0.05)_100%)]"
      />
      <div
        aria-hidden="true"
        className="absolute inset-x-0 bottom-0 -z-10 h-2/5 bg-[linear-gradient(180deg,transparent,rgb(5_18_12/0.7))]"
      />

      <div className="container-page grid content-center gap-12 py-16 sm:py-20 lg:min-h-[min(calc(100svh-72px),840px)] lg:grid-cols-[1.45fr_0.75fr] lg:items-center lg:gap-10 lg:py-24">
        {/* Copy */}
        <div>
          <p className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/10 px-3.5 py-1.5 text-[13px] font-semibold text-white backdrop-blur-md">
            <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ff9a7a" strokeWidth="2.2" strokeLinejoin="round">
              <path d="M13 2L4 14h7l-1 8 9-12h-7z" />
            </svg>
            {hero.eyebrow}
          </p>
          <h1
            id="hero-heading"
            className="mt-6 font-display text-[40px] font-extrabold leading-[1.05] tracking-[-0.03em] text-white [text-shadow:0_2px_24px_rgb(0_0_0/0.25)] sm:text-[56px] lg:text-[64px]"
          >
            {hero.headline.before}
            <span className="text-[#ffa27f]">{hero.headline.highlight}</span>
            {hero.headline.after}
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-white/85 sm:text-xl">{hero.subtext}</p>
          <div className="mt-9 flex flex-col items-start gap-5 sm:flex-row sm:items-center sm:gap-7">
            <GetStarted size="lg" onDark />
            <a
              href={links.whatsappUrl}
              rel="noopener"
              className="text-[16px] font-semibold text-white underline decoration-[#ffa27f] decoration-2 underline-offset-4 hover:text-[#ffd2c2]"
            >
              {hero.farmerLink}
            </a>
          </div>

          {/* Stats */}
          <div className="mt-14">
            <h2 className="sr-only">{statsHeading}</h2>
            <dl className="grid max-w-2xl grid-cols-2 gap-x-8 gap-y-6 sm:grid-cols-4 sm:gap-x-6">
              {stats.map((s) => (
                <div key={s.label} className="flex flex-col gap-1 border-l-2 border-white/20 pl-4">
                  <dt className="order-2 whitespace-nowrap text-[13.5px] text-white/80">{s.label}</dt>
                  <dd className="order-1 font-display text-[30px] font-extrabold leading-none tracking-[-0.02em] text-white tabular-nums sm:text-[34px]">
                    <CountUp display={s.display} countTo={s.countTo} />
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </div>

        {/* Glass feature cards */}
        <ul className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1 lg:gap-4 lg:self-center lg:justify-self-end lg:w-full lg:max-w-[340px]">
          {hero.cards.map((c) => {
            const Icon = stepIcons[c.icon];
            return (
              <li
                key={c.title}
                className="flex gap-4 rounded-[16px] border border-white/20 bg-[rgb(10_34_24/0.45)] p-4 shadow-[0_10px_30px_-12px_rgb(0_0_0/0.5)] backdrop-blur-md sm:p-5"
              >
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-[10px] bg-white/10">
                  <Icon size={21} className="text-[#ffa27f]" />
                </span>
                <span>
                  <span className="block font-display text-[16px] font-bold leading-snug text-white">{c.title}</span>
                  <span className="mt-1 block text-[14px] leading-snug text-white/80">{c.body}</span>
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
