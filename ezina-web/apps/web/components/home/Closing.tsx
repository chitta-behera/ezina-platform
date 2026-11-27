import { closing, contactHref, links } from "@/content/site";
import { GetStarted } from "../GetStarted";
import { MailIcon } from "../icons";

export function Closing() {
  return (
    <section aria-labelledby="closing-heading" className="py-16 sm:py-20">
      <div className="container-page">
        <div className="hero-bg relative overflow-hidden rounded-[24px] border border-line px-6 py-12 text-center shadow-[0_20px_50px_-30px_rgba(12,30,52,0.35)] sm:px-12 sm:py-16">
          <h2
            id="closing-heading"
            className="mx-auto max-w-3xl font-display text-[30px] font-extrabold leading-[1.12] tracking-[-0.02em] text-navy-deep sm:text-[42px]"
          >
            {closing.heading}
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-muted">{closing.body}</p>
          <div className="mt-8 flex flex-col items-center justify-center gap-5 sm:flex-row sm:gap-7">
            <GetStarted size="lg" />
            <a
              href={contactHref}
              className="inline-flex items-center gap-2 text-[16px] font-semibold text-navy underline decoration-orange decoration-2 underline-offset-4"
            >
              <MailIcon size={20} className="text-orange-ink" />
              {closing.talkToUs}
            </a>
          </div>
          <p className="mt-6">
            <a href={links.whatsappUrl} rel="noopener" className="text-[15px] font-semibold text-orange-ink underline underline-offset-4">
              {closing.farmerLink}
            </a>
          </p>
        </div>
      </div>
    </section>
  );
}
