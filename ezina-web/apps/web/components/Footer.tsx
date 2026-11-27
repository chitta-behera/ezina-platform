import { Logo } from "@ezina/ui";
import { footer, header, links, nav } from "@/content/site";
import { FloatingWhatsApp } from "./FloatingWhatsApp";

const linkCls = "text-[#dde4ec] no-underline hover:text-white hover:underline";

export function Footer() {
  return (
    <footer className="bg-navy-deep pb-24 pt-14 text-[#c3cedb] md:pb-12">
      <div className="container-page">
        <div className="grid gap-10 md:grid-cols-[1.3fr_1fr_1fr]">
          <div>
            <Logo height={64} />
            <p className="mt-4 font-display text-lg font-semibold text-white">{footer.tagline}</p>
            <p className="mt-2 text-[15px]">{footer.footprint}</p>
          </div>
          <nav aria-label="Footer">
            <h2 className="text-[13px] font-bold uppercase tracking-[0.14em] text-orange-soft">Explore</h2>
            <ul className="mt-3 space-y-2 text-[15px]">
              {nav.map((item) => (
                <li key={item.href}>
                  <a href={item.href} className={linkCls}>
                    {item.label}
                  </a>
                </li>
              ))}
              <li>
                <a href={links.whatsappUrl} rel="noopener" className={linkCls}>
                  {header.farmersLink}
                </a>
              </li>
            </ul>
          </nav>
          <div>
            <h2 className="text-[13px] font-bold uppercase tracking-[0.14em] text-orange-soft">Contact</h2>
            <ul className="mt-3 space-y-2 text-[15px]">
              <li>
                <a href={`mailto:${links.email}`} className="text-[#dde4ec] underline hover:text-white">
                  {links.email}
                </a>
              </li>
              <li>
                <a href={links.linkedin} rel="noopener" className={linkCls}>
                  LinkedIn
                </a>
              </li>
              <li>
                <a href={links.x} rel="noopener" className={linkCls}>
                  X ({links.xHandle})
                </a>
              </li>
              {footer.legal.map((l) => (
                <li key={l.href}>
                  <a href={l.href} className={linkCls}>
                    {l.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <p className="mt-12 border-t border-navy-line pt-6 text-[13.5px] leading-relaxed text-[#a9b6c4]">
          {footer.copyright} {footer.disclaimer}
        </p>
      </div>
      {/* Fixed-position mobile shortcut; lives in the footer landmark for screen readers. */}
      <FloatingWhatsApp />
    </footer>
  );
}
