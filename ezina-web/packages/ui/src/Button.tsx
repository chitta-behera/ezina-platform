import type { AnchorHTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

export type ButtonVariant = "primary" | "outline" | "ghost-light" | "link";
export type ButtonSize = "sm" | "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 font-semibold no-underline transition-colors rounded-[var(--radius-btn)] focus-visible:outline-offset-2";

const variants: Record<ButtonVariant, string> = {
  primary: "bg-orange-strong text-white border-2 border-orange-strong hover:bg-orange-stronger hover:border-orange-stronger",
  outline: "bg-transparent text-navy border-2 border-navy/25 hover:border-navy",
  "ghost-light": "bg-transparent text-white border-2 border-white/55 hover:border-white",
  link: "text-orange-ink underline underline-offset-4 decoration-2 hover:text-orange-stronger px-0",
};

const sizes: Record<ButtonSize, string> = {
  sm: "text-[15px] px-4 py-2",
  md: "text-base px-5 py-3",
  lg: "text-[17px] px-6 py-3.5",
};

export type ButtonLinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & {
  href: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
};

/** A link styled as a button. Everything on the marketing site navigates, so buttons are anchors. */
export function ButtonLink({ variant = "primary", size = "md", className, children, ...rest }: ButtonLinkProps) {
  return (
    <a className={cn(base, variants[variant], variant === "link" ? "" : sizes[size], className)} {...rest}>
      {children}
    </a>
  );
}

/** Class string for a real <button> that should look like ButtonLink. */
export function buttonClasses(variant: ButtonVariant = "primary", size: ButtonSize = "md", className?: string) {
  return cn(base, variants[variant], sizes[size], "cursor-pointer", className);
}
