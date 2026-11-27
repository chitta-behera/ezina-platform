import { floatingWhatsApp, links } from "@/content/site";
import { ChatIcon } from "./icons";

/**
 * Small farmer WhatsApp shortcut, mobile only. Pure link, no JavaScript of its own.
 * Hidden while the WhatsApp demo section is on screen (`html[data-demo-in-view]`, set by DemoShowcase) so it
 * never covers the demo's step controls.
 */
export function FloatingWhatsApp() {
  return (
    <a
      href={links.whatsappUrl}
      rel="noopener"
      aria-label={floatingWhatsApp.label}
      className="floating-wa fixed bottom-4 right-4 z-30 inline-flex items-center gap-1.5 rounded-full bg-[#0b6e4f] py-2 pl-2.5 pr-3.5 text-[13.5px] font-semibold text-white no-underline shadow-[0_6px_18px_rgba(0,0,0,0.25)] md:hidden"
    >
      <ChatIcon size={18} />
      <span aria-hidden="true">{floatingWhatsApp.short}</span>
    </a>
  );
}
