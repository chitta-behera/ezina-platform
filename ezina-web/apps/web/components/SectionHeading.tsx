import { cn } from "@ezina/ui";

type Props = {
  eyebrow?: string;
  heading: string;
  intro?: string;
  id?: string;
  center?: boolean;
  onDark?: boolean;
  className?: string;
};

export function SectionHeading({ eyebrow, heading, intro, id, center, onDark, className }: Props) {
  return (
    <div className={cn("max-w-3xl", center && "mx-auto text-center", className)}>
      {eyebrow && (
        <p
          className={cn(
            "mb-3 text-[13px] font-bold uppercase tracking-[0.16em]",
            onDark ? "text-orange-soft" : "text-orange-ink",
          )}
        >
          {eyebrow}
        </p>
      )}
      <h2
        id={id}
        className={cn(
          "font-display text-[28px] font-bold leading-[1.15] tracking-[-0.02em] sm:text-4xl",
          onDark ? "text-white" : "text-navy-deep",
        )}
      >
        {heading}
      </h2>
      {intro && <p className={cn("mt-4 text-[17px] sm:text-lg", onDark ? "text-[#c3cedb]" : "text-muted")}>{intro}</p>}
    </div>
  );
}
