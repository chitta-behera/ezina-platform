import { cn } from "./cn";

/** Intrinsic size of the official logo file served at /images/logo.webp (margin trimmed, artwork untouched). */
const LOGO_W = 159;
const LOGO_H = 128;

export type LogoProps = {
  /** Path to the official logo image, served by the app. */
  src?: string;
  /** Display height in CSS pixels; width follows the logo's own proportions. */
  height?: number;
  className?: string;
};

/**
 * The official Ezina logo (sunrise bridge + wordmark), shown as-is: no recolouring or cropping of the artwork.
 * It has its own cream background, so it reads the same on light and dark sections (a cream tile on dark).
 */
export function Logo({ src = "/images/logo.webp", height = 56, className }: LogoProps) {
  const width = Math.round((LOGO_W / LOGO_H) * height);
  return (
    <img
      src={src}
      alt="Ezina"
      width={width}
      height={height}
      style={{ width, height }}
      className={cn("block shrink-0 rounded-[10px]", className)}
      decoding="async"
    />
  );
}
