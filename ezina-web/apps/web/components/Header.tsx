import Link from "next/link";
import { ButtonLink, Logo } from "@ezina/ui";
import { contactHref, header, links, loginUrl, nav } from "@/content/site";
import { MobileMenu } from "./MobileMenu";

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-cream">
      <a href="#main" className="sr-only-focusable absolute left-3 top-3 z-50 rounded bg-navy px-3 py-2 text-white">
        {header.skipToContent}
      </a>
      <div className="container-page relative flex h-[72px] items-center justify-between gap-4">
        <Link href="/" className="shrink-0 rounded-md" aria-label="Ezina home">
          <Logo height={56} />
        </Link>

        <nav aria-label="Main" className="hidden lg:block">
          <ul className="flex items-center gap-7 text-[15px] font-medium">
            {nav.map((item) => (
              <li key={item.href}>
                <a
                  href={item.href}
                  className="text-navy no-underline hover:underline hover:decoration-orange hover:decoration-2 hover:underline-offset-4"
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex items-center gap-3 sm:gap-4">
          <a
            href={links.whatsappUrl}
            rel="noopener"
            className="hidden text-[13.5px] font-medium text-muted underline-offset-4 hover:text-navy hover:underline xl:inline"
          >
            {header.farmersLink}
          </a>
          {loginUrl && (
            <a href={loginUrl} className="hidden text-[15px] font-semibold text-navy hover:underline sm:inline">
              {header.login}
            </a>
          )}
          {/* Main header action. "Get Started" is hidden here until the app launches (getStartedUrl in site.ts). */}
          <ButtonLink href={contactHref} size="sm" className="whitespace-nowrap">
            {header.talkToUs}
          </ButtonLink>
          <MobileMenu label={header.menu}>
            <nav aria-label="Mobile" className="container-page py-3">
              <ul className="flex flex-col">
                {nav.map((item) => (
                  <li key={item.href}>
                    <a
                      href={item.href}
                      className="block border-b border-line py-3 text-[17px] font-medium text-navy no-underline"
                    >
                      {item.label}
                    </a>
                  </li>
                ))}
                {loginUrl && (
                  <li>
                    <a
                      href={loginUrl}
                      className="block border-b border-line py-3 text-[17px] font-medium text-navy no-underline"
                    >
                      {header.login}
                    </a>
                  </li>
                )}
                <li>
                  <a href={links.whatsappUrl} rel="noopener" className="block py-3 text-[15px] font-medium text-muted">
                    {header.farmersLink}
                  </a>
                </li>
                <li className="pb-2 pt-2">
                  <ButtonLink href={contactHref} size="md" className="w-full">
                    {header.talkToUs}
                  </ButtonLink>
                </li>
              </ul>
            </nav>
          </MobileMenu>
        </div>
      </div>
    </header>
  );
}
