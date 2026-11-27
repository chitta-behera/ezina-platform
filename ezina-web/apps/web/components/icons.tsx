import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 24, children, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const ChatIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M21 12a8 8 0 0 1-11.7 7.1L4 20l1.1-4.8A8 8 0 1 1 21 12z" />
    <path d="M8.5 11h7M8.5 14h4" />
  </Svg>
);

export const ShieldIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3l7 3v6c0 4.4-3 7.8-7 9-4-1.2-7-4.6-7-9V6l7-3z" />
    <path d="M9 12l2 2 4-4" />
  </Svg>
);

export const LinkIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" />
    <path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />
  </Svg>
);

export const TrackIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 20h16" />
    <path d="M5 16l4-4 3 3 6-6" />
    <path d="M15 9h3v3" />
  </Svg>
);

export const CheckIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </Svg>
);

export const AlertIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7.5v5.5M12 16.5v.01" />
  </Svg>
);

export const MinusCircleIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M8 12h8" />
  </Svg>
);

export const PinIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 21s-6.5-5.8-6.5-11a6.5 6.5 0 0 1 13 0c0 5.2-6.5 11-6.5 11z" />
    <circle cx="12" cy="10" r="2.3" />
  </Svg>
);

export const MailIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="M3.5 6.5L12 13l8.5-6.5" />
  </Svg>
);

export const ArrowRightIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Svg>
);

export const MenuIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Svg>
);

export const PlusIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);

/** Double "read" ticks used in chat mockups. */
export const ReadTicks = (p: IconProps) => (
  <svg width={16} height={11} viewBox="0 0 16 11" aria-hidden="true" focusable="false" {...p}>
    <path d="M1 5.8l2.8 2.8L10 2.2" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M6.2 8.4l.2.2L12.6 2.2" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const stepIcons = { chat: ChatIcon, shield: ShieldIcon, link: LinkIcon, track: TrackIcon } as const;

/** Farmers: a sprouting seedling. */
export const SproutIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 21v-9" />
    <path d="M12 12c0-4 2.8-6.5 7-6.5 0 4.2-2.8 6.5-7 6.5z" />
    <path d="M12 14.5c0-3.4-2.4-5.5-6-5.5 0 3.5 2.4 5.5 6 5.5z" />
    <path d="M7 21h10" />
  </Svg>
);

/** Buyers: a produce crate. */
export const CrateIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3.5 9.5h17l-1.6 9.6a1.5 1.5 0 0 1-1.5 1.4H6.6a1.5 1.5 0 0 1-1.5-1.4z" />
    <path d="M8.5 13v4M12 13v4M15.5 13v4" />
    <circle cx="8.5" cy="6.5" r="2.5" />
    <circle cx="14.5" cy="6" r="3" />
  </Svg>
);

/** Institutions: a building with columns. */
export const BuildingIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 9.5L12 4l9 5.5" />
    <path d="M5 10v8M9.7 10v8M14.3 10v8M19 10v8" />
    <path d="M3 20.5h18" />
  </Svg>
);

/** Export partners: a globe. */
export const GlobeIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18" />
    <path d="M12 3c2.6 2.6 3.8 5.6 3.8 9s-1.2 6.4-3.8 9c-2.6-2.6-3.8-5.6-3.8-9S9.4 5.6 12 3z" />
  </Svg>
);

export const audienceIcons = { sprout: SproutIcon, crate: CrateIcon, building: BuildingIcon, globe: GlobeIcon } as const;

/** Market intelligence: a rising bar chart. */
export const ChartIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 20h16" />
    <path d="M7 16v-4M12 16V8M17 16v-7" />
    <path d="M5 9l5-4 4 3 5-4" />
  </Svg>
);

/** Reduced risk: a shield with a downward arrow. */
export const RiskIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3l7 3v6c0 4.4-3 7.8-7 9-4-1.2-7-4.6-7-9V6l7-3z" />
    <path d="M12 8v7M9 12.5l3 3 3-3" />
  </Svg>
);

/** Greater opportunities: a sparkle. */
export const SparkIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />
    <path d="M18.5 16l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z" />
  </Svg>
);

/** No cut taken: a coin with a slash. */
export const NoCutIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M14.5 9.2c-.6-.8-1.5-1.2-2.6-1.2-1.6 0-2.7.9-2.7 2s1 1.6 2.8 2 2.8 1 2.8 2.1-1.2 2-2.8 2c-1.2 0-2.2-.5-2.8-1.3M12 6.5v1.5M12 16v1.5" />
    <path d="M4.5 4.5l15 15" />
  </Svg>
);

export const whyIcons = { shield: ShieldIcon, chart: ChartIcon, link: LinkIcon, risk: RiskIcon, spark: SparkIcon } as const;
