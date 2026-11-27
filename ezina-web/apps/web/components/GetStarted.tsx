import { ButtonLink, cn, type ButtonSize } from "@ezina/ui";
import { getStarted, getStartedUrl } from "@/content/site";

const sizes: Record<ButtonSize, string> = {
  sm: "text-[15px] px-4 py-2",
  md: "text-base px-5 py-3",
  lg: "text-[17px] px-6 py-3.5",
};

/**
 * Every "Get Started" on the site. With getStartedUrl set it is a normal link; with null (app not ready) it is a
 * disabled button with a "Coming soon" badge: no href, not focusable, aria-disabled.
 * The small size puts the badge on the corner so it fits a 375px-wide header.
 */
export function GetStarted({
  size = "md",
  label = getStarted.label,
  onDark = false,
  className,
}: {
  size?: ButtonSize;
  label?: string;
  /** Frosted-glass style for photo or dark backgrounds. */
  onDark?: boolean;
  className?: string;
}) {
  if (getStartedUrl) {
    return (
      <ButtonLink href={getStartedUrl} size={size} className={className}>
        {label}
      </ButtonLink>
    );
  }

  const corner = size === "sm";
  return (
    <button
      type="button"
      disabled
      aria-disabled="true"
      className={cn(
        "relative inline-flex shrink-0 cursor-not-allowed whitespace-nowrap items-center justify-center gap-2.5 rounded-[var(--radius-btn)] border-2 border-dashed font-semibold",
        onDark
          ? "border-white/45 bg-white/12 text-white backdrop-blur-md"
          : "border-[#cfc6b3] bg-[#efebe2] text-[#4a5561]",
        sizes[size],
        className,
      )}
    >
      {label}
      <span
        className={cn(
          "whitespace-nowrap rounded-full bg-orange-strong font-bold uppercase tracking-[0.06em] text-white",
          corner
            ? "absolute -right-2 -top-2.5 px-1.5 py-[1px] text-[9.5px] leading-[14px] shadow-sm"
            : "px-2 py-0.5 text-[11px] leading-4",
        )}
      >
        <span className="sr-only">(</span>
        {getStarted.comingSoon}
        <span className="sr-only">)</span>
      </span>
    </button>
  );
}
