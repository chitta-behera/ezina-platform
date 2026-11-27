import type { Metadata } from "next";
import { contactPage as c, links } from "@/content/site";
import { pageMetadata } from "@/lib/metadata";
import { ContactForm } from "@/components/ContactForm";
import { ChatIcon, MailIcon, PinIcon } from "@/components/icons";

export const metadata: Metadata = pageMetadata({ path: "/contact", title: c.title, description: c.description });

/**
 * /contact ("Talk to us"). Layout and form style modelled on a dark "Get in touch" section (pill fields, two columns,
 * outlined pill button), in Ezina's colours and fonts. No CAPTCHA. Submission: lib/contact.ts (mock now, API later).
 */
export default function ContactPage() {
  return (
    <section aria-labelledby="contact-heading" className="relative overflow-hidden bg-navy-deep text-white">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-40 -top-40 h-[520px] w-[520px] rounded-full opacity-40 blur-3xl [background:radial-gradient(circle,rgb(252_74_26/0.45),transparent_65%)]"
      />
      <div className="container-page relative grid gap-10 py-14 sm:py-20 lg:grid-cols-[1.65fr_1fr] lg:gap-14">
        <div>
          <p className="text-[13px] font-bold uppercase tracking-[0.16em] text-orange-soft">{c.eyebrow}</p>
          <h1 id="contact-heading" className="mt-3 font-display text-[36px] font-bold leading-[1.08] tracking-[-0.02em] text-white sm:text-[48px]">
            {c.heading}
          </h1>
          <p className="mt-4 max-w-2xl text-[17px] leading-relaxed text-[#c3cedb] sm:text-lg">{c.intro}</p>
          <div className="mt-10">
            <ContactForm />
          </div>
        </div>

        <aside aria-labelledby="contact-aside" className="lg:pt-[150px]">
          <div className="rounded-[24px] border border-navy-line bg-navy-card p-6 sm:p-7">
            <h2 id="contact-aside" className="font-display text-[19px] font-bold text-white">
              {c.aside.heading}
            </h2>
            <dl className="mt-5 space-y-5 text-[15.5px]">
              <div>
                <dt className="flex items-center gap-2 text-[12.5px] font-bold uppercase tracking-[0.12em] text-[#8597aa]">
                  <MailIcon size={16} /> {c.aside.emailLabel}
                </dt>
                <dd className="mt-1">
                  <a href={`mailto:${links.email}`} className="font-semibold text-white underline decoration-orange-soft underline-offset-4 hover:text-orange-soft">
                    {links.email}
                  </a>
                </dd>
              </div>
              <div>
                <dt className="sr-only">WhatsApp</dt>
                <dd>
                  <a href={links.whatsappUrl} rel="noopener" className="inline-flex items-start gap-2 font-semibold text-[#8fd4ac] underline underline-offset-4 hover:text-white">
                    <ChatIcon size={18} className="mt-0.5 shrink-0" />
                    {c.aside.farmers}
                  </a>
                </dd>
              </div>
              <div>
                <dt className="flex items-center gap-2 text-[12.5px] font-bold uppercase tracking-[0.12em] text-[#8597aa]">
                  <PinIcon size={16} /> {c.aside.whereLabel}
                </dt>
                <dd className="mt-1 text-[#dde4ec]">{c.aside.where}</dd>
              </div>
              <div>
                <dt className="text-[12.5px] font-bold uppercase tracking-[0.12em] text-[#8597aa]">{c.aside.socialLabel}</dt>
                <dd className="mt-2 flex gap-3">
                  <a href={links.linkedin} rel="noopener" aria-label="Ezina on LinkedIn" className="grid h-10 w-10 place-items-center rounded-full border border-navy-line text-[#dde4ec] hover:border-white hover:text-white">
                    <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M4.98 3.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5zM3 9.75h4v11.5H3zM9.5 9.75h3.8v1.6h.06c.53-1 1.83-2.05 3.77-2.05 4.03 0 4.77 2.6 4.77 6v5.95h-4v-5.27c0-1.26-.02-2.88-1.76-2.88-1.76 0-2.03 1.37-2.03 2.79v5.36h-4z" />
                    </svg>
                  </a>
                  <a href={links.x} rel="noopener" aria-label={`Ezina on X (${links.xHandle})`} className="grid h-10 w-10 place-items-center rounded-full border border-navy-line text-[#dde4ec] hover:border-white hover:text-white">
                    <svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M17.75 3h3.07l-6.7 7.66L22 21h-6.17l-4.83-6.32L5.47 21H2.4l7.17-8.2L2 3h6.33l4.37 5.77zm-1.08 16.2h1.7L7.4 4.73H5.58z" />
                    </svg>
                  </a>
                </dd>
              </div>
            </dl>
          </div>
        </aside>
      </div>
    </section>
  );
}
