import type { ReactNode } from "react";
import { cn } from "@ezina/ui";
import type { ChatMessage } from "@/content/site";

/** WhatsApp-like colours (classic green theme). No WhatsApp logo or trademarked assets are used. */
const GREEN = "#075e54";
const OUT = "#d9fdd3";

/**
 * A modern phone (thin bezels, dynamic island, status bar) showing an Ezina chat.
 * Sized by height (fits the viewport, max 678px) with a 9:18 aspect ratio; `children` fills the chat area between
 * the header and the input bar (the caller makes it scroll).
 */
export function PhoneFrame({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        // Max 678px (owner: version B + another 10%), capped by the viewport so the section fits one screen.
        // Tablets (md) get their own cap: heading and intro sit above the phone there. Width follows the 9:18 ratio.
        "relative aspect-[9/18] h-[min(678px,82svh,calc(100svh_-_254px))] rounded-[40px] bg-[#16191d] p-[6px] md:h-[min(678px,calc(100svh_-_386px))] lg:h-[min(678px,calc(100svh_-_168px))]",
        "shadow-[0_50px_80px_-30px_rgb(8_22_39/0.55),0_20px_40px_-20px_rgb(8_22_39/0.35),inset_0_0_0_1.5px_rgb(255_255_255/0.08)]",
        className,
      )}
    >
      {/* Side buttons */}
      <span aria-hidden="true" className="absolute -left-[3px] top-[18%] h-7 w-[3px] rounded-l bg-[#2a2f35]" />
      <span aria-hidden="true" className="absolute -left-[3px] top-[26%] h-12 w-[3px] rounded-l bg-[#2a2f35]" />
      <span aria-hidden="true" className="absolute -right-[3px] top-[22%] h-16 w-[3px] rounded-r bg-[#2a2f35]" />

      <div className="relative flex h-full flex-col overflow-hidden rounded-[34px] bg-[#efeae2]">
        <StatusBar />
        <ChatHeader />
        <div className="chat-wallpaper-topo relative min-h-0 flex-1">{children}</div>
        <InputBar />
        {/* Home indicator */}
        <span aria-hidden="true" className="absolute bottom-1 left-1/2 h-1 w-24 -translate-x-1/2 rounded-full bg-black/25" />
      </div>
    </div>
  );
}

function StatusBar() {
  return (
    <div aria-hidden="true" className="relative flex h-8 shrink-0 items-end justify-between px-6 pb-1 text-[11.5px] font-semibold text-white" style={{ background: GREEN }}>
      <span>9:41</span>
      <span className="absolute left-1/2 top-1.5 h-5 w-[72px] -translate-x-1/2 rounded-full bg-[#0b0d0f]" />
      <span className="flex items-center gap-1.5">
        <svg width="14" height="9" viewBox="0 0 17 11" fill="currentColor">
          <rect x="0" y="7" width="3" height="4" rx="0.8" />
          <rect x="4.6" y="5" width="3" height="6" rx="0.8" />
          <rect x="9.2" y="2.5" width="3" height="8.5" rx="0.8" />
          <rect x="13.8" y="0" width="3" height="11" rx="0.8" />
        </svg>
        <svg width="13" height="10" viewBox="0 0 15 11" fill="currentColor">
          <path d="M7.5 2.2c2.2 0 4.2.8 5.7 2.2l1.2-1.3A10 10 0 0 0 7.5.4 10 10 0 0 0 .6 3.1l1.2 1.3A8.2 8.2 0 0 1 7.5 2.2zm0 3.4c1.3 0 2.5.5 3.4 1.3l1.2-1.3A6.7 6.7 0 0 0 7.5 3.8c-1.8 0-3.4.7-4.6 1.8l1.2 1.3c.9-.8 2.1-1.3 3.4-1.3zm0 3.3c.5 0 .9.2 1.2.5L7.5 10.8 6.3 9.4c.3-.3.7-.5 1.2-.5z" />
        </svg>
        <svg width="21" height="10" viewBox="0 0 25 12" fill="none">
          <rect x="0.5" y="0.5" width="21" height="11" rx="3.5" stroke="currentColor" opacity="0.45" />
          <rect x="2" y="2" width="16" height="8" rx="2" fill="currentColor" />
          <path d="M23 4v4a2 2 0 0 0 0-4z" fill="currentColor" opacity="0.45" />
        </svg>
      </span>
    </div>
  );
}

function ChatHeader() {
  return (
    <div className="flex h-11 shrink-0 items-center gap-1.5 px-2 text-white" style={{ background: GREEN }}>
      <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" className="shrink-0">
        <path d="M20 12H5m6-7-7 7 7 7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <img
        src="/images/logo-avatar.webp"
        alt="Ezina"
        width={30}
        height={30}
        className="h-[30px] w-[30px] shrink-0 rounded-full bg-[#fdfcf7]"
        decoding="async"
      />
      <div className="min-w-0 flex-1 pl-0.5 leading-tight">
        <p className="text-[14px] font-semibold">Ezina</p>
        <p className="text-[11px] text-white/80">online</p>
      </div>
      <span aria-hidden="true" className="flex items-center gap-[13px] pr-1">
        {/* Video call */}
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <path d="M3.5 6.5A2.5 2.5 0 0 1 6 4h8a2.5 2.5 0 0 1 2.5 2.5v11A2.5 2.5 0 0 1 14 20H6a2.5 2.5 0 0 1-2.5-2.5zM18 9.6l3.1-2.2c.6-.4 1.4 0 1.4.8v7.6c0 .8-.8 1.2-1.4.8L18 14.4z" />
        </svg>
        {/* Voice call (handset) */}
        <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
          <path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1A17 17 0 0 1 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.3 0 .7-.2 1z" />
        </svg>
        {/* Menu */}
        <svg width="3.5" height="15" viewBox="0 0 4 18" fill="currentColor">
          <circle cx="2" cy="2.5" r="2" />
          <circle cx="2" cy="9" r="2" />
          <circle cx="2" cy="15.5" r="2" />
        </svg>
      </span>
    </div>
  );
}

function InputBar() {
  return (
    <div aria-hidden="true" className="flex shrink-0 items-center gap-1 px-1.5 pb-4 pt-1">
      <div className="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-full bg-white px-2.5 text-[#54656f] shadow-[0_1px_0.5px_rgb(11_20_26/0.13)]">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" className="shrink-0">
          <circle cx="12" cy="12" r="9" />
          <path d="M8.5 14.2a4.6 4.6 0 0 0 7 0" />
          <circle cx="9" cy="9.8" r="0.6" fill="currentColor" strokeWidth="1.4" />
          <circle cx="15" cy="9.8" r="0.6" fill="currentColor" strokeWidth="1.4" />
        </svg>
        <span className="min-w-0 flex-1 truncate text-[13px] text-[#667781]">Message</span>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" className="shrink-0 -rotate-45">
          <path d="M20 11.5l-8.2 8.2a5 5 0 0 1-7.1-7.1l8.6-8.6a3.3 3.3 0 0 1 4.7 4.7l-8.6 8.6a1.7 1.7 0 0 1-2.4-2.4l7.9-7.9" />
        </svg>
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" className="shrink-0">
          <path d="M8.6 5h6.8l1.5 2.2H20a1 1 0 0 1 1 1V18a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8.2a1 1 0 0 1 1-1h3.1z" />
          <circle cx="12" cy="12.8" r="3.4" />
        </svg>
      </div>
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#00a884] text-white shadow-[0_1px_2px_rgb(11_20_26/0.25)]">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <rect x="9" y="2.5" width="6" height="11.5" rx="3" fill="currentColor" />
          <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21.5" />
        </svg>
      </div>
    </div>
  );
}

/** Render WhatsApp-style *bold* inside a line. */
function formatLine(line: string) {
  return line.split(/(\*[^*\n]+\*)/g).map((part, i) =>
    part.startsWith("*") && part.endsWith("*") && part.length > 2 ? (
      <strong key={i} className="font-semibold">
        {part.slice(1, -1)}
      </strong>
    ) : (
      part
    ),
  );
}

const shadow = "shadow-[0_1px_0.5px_rgb(11_20_26/0.13)]";

/**
 * One chat bubble. `first` = first in a run from the same sender (gets the tail).
 * Quick-reply buttons (`m.buttons`) sit under the bubble; `hideButtons` keeps them back during the animation and
 * `tapped` briefly highlights one, as if the farmer had just tapped it.
 */
export function Bubble({
  m,
  first,
  hideButtons = false,
  tapped = null,
  className,
}: {
  m: ChatMessage;
  first: boolean;
  hideButtons?: boolean;
  tapped?: string | null;
  className?: string;
}) {
  const out = m.from === "farmer"; // the phone belongs to the farmer: their messages are outgoing (right, green)
  const bg = out ? OUT : "#ffffff";
  const withButtons = !!m.buttons?.length && !hideButtons;
  return (
    <li className={cn("flex flex-col", out ? "items-end" : "items-start", first ? "mt-1.5" : "mt-[2px]", className)}>
      <div
        className={cn(
          "relative max-w-[86%] rounded-[8px] px-[7px] pb-[3px] pt-1 text-[13px] leading-[1.35] text-[#111b21]",
          shadow,
          first && (out ? "rounded-tr-none" : "rounded-tl-none"),
          m.location && "p-1",
          withButtons && "w-[86%] rounded-b-none",
        )}
        style={{ background: bg }}
      >
        {first && (
          <span
            aria-hidden="true"
            className={cn(
              "absolute top-0 h-3 w-2",
              out ? "-right-[7px] [clip-path:polygon(0_0,100%_0,0_100%)]" : "-left-[7px] [clip-path:polygon(0_0,100%_0,100%_100%)]",
            )}
            style={{ background: bg }}
          />
        )}
        <span className="sr-only">{out ? "Farmer: " : "Ezina: "}</span>

        {m.location ? (
          <span className="block w-[160px]">
            <span aria-hidden="true" className="chat-map relative block h-[68px] overflow-hidden rounded-[6px]">
              <svg width="22" height="28" viewBox="0 0 30 38" className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-[80%] drop-shadow">
                <path d="M15 37s13-13.4 13-22A13 13 0 0 0 2 15c0 8.6 13 22 13 22z" fill="#e53935" />
                <circle cx="15" cy="15" r="5" fill="#fff" />
              </svg>
            </span>
            <span className="block px-1.5 pb-0.5 pt-1.5">
              📍 <strong className="font-semibold">{m.location}</strong>
              <span className="block text-[11px] text-[#54656f]">Shared location</span>
            </span>
          </span>
        ) : (
          m.text?.split("\n").map((line, i) => (
            <span key={i} className="block">
              {formatLine(line)}
            </span>
          ))
        )}

        <span className={cn("float-right ml-2 mt-[3px] flex items-center gap-[3px] text-[10px] leading-none text-[#54656f]", m.location && "mr-1")}>
          <span>{m.time}</span>
          {out && (
            <>
              <svg aria-hidden="true" width="14" height="10" viewBox="0 0 16 11" className="text-[#53bdeb]">
                <path d="M1 5.8l2.8 2.8L10 2.2M6.2 8.4l.2.2 6.2-6.4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="sr-only">(read)</span>
            </>
          )}
        </span>
        <span className="clear-both block" />
      </div>
      {withButtons && (
        <ul
          aria-label="Reply options"
          className={cn("demo-pop flex w-[86%] flex-col overflow-hidden rounded-b-[8px] border-t border-black/[0.07] bg-white", shadow)}
        >
          {m.buttons!.map((b, i) => (
            <li
              key={b}
              className={cn(
                "flex items-center justify-center gap-1.5 px-2 py-[7px] text-center text-[13px] font-medium text-[#008069] transition-[background-color,transform] duration-200",
                i > 0 && "border-t border-black/[0.07]",
                tapped === b && "scale-[0.98] bg-[#d9f2ec]",
              )}
            >
              <svg aria-hidden="true" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 14L4 9l5-5" />
                <path d="M4 9h10a6 6 0 0 1 6 6v5" />
              </svg>
              {b}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** Ezina's "typing…" bubble. */
export function TypingBubble({ className }: { className?: string }) {
  return (
    <li className={cn("mt-1.5 flex justify-start", className)}>
      <span className={cn("relative inline-flex items-center gap-1 rounded-[8px] rounded-tl-none bg-white px-3 py-2.5", shadow)}>
        <span aria-hidden="true" className="absolute -left-[7px] top-0 h-3 w-2 bg-white [clip-path:polygon(0_0,100%_0,100%_100%)]" />
        <span className="sr-only">Ezina is typing</span>
        <span aria-hidden="true" className="chat-dot" />
        <span aria-hidden="true" className="chat-dot [animation-delay:0.18s]" />
        <span aria-hidden="true" className="chat-dot [animation-delay:0.36s]" />
      </span>
    </li>
  );
}
