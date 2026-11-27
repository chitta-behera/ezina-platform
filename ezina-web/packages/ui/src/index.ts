export { ButtonLink, buttonClasses } from "./Button";
export type { ButtonLinkProps, ButtonVariant, ButtonSize } from "./Button";
export { Logo } from "./Logo";
export type { LogoProps } from "./Logo";
export { cn } from "./cn";

/** Brand colour values for non-CSS contexts (e.g. generated images, theme-color meta). */
export const brand = {
  navy: "#0c1e34",
  navyDeep: "#081627",
  cream: "#fdfcf7",
  orange: "#fc4a1a",
  orangeStrong: "#d4370c",
} as const;
