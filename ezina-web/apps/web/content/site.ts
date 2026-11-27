/**
 * Ezina marketing site: ALL copy, stats, FAQs, links and flags live here.
 * Edit this file to change the site; components only render what is here.
 *
 * Placeholders: anything containing "[TODO" still needs real content. Search for "[TODO" to find them all.
 * Honesty rules (from the original site): say what is verified and what is uncertain; verification never
 * guarantees a sale, price or payment; do not add customers, numbers, quotes or results that are not real.
 */

// ---------------------------------------------------------------------------
// Flags and links
// ---------------------------------------------------------------------------

export const siteUrl = "https://www.ezina.ai";

export const links = {
  /** wa.me needs the number without "+". */
  whatsappUrl: "https://wa.me/26774257916?text=Hi%20Ezina",
  appUrl: "https://app.ezina.ai",
  signupPath: "/signup",
  loginPath: "/login",
  email: "hello@ezina.ai",
  linkedin: "https://www.linkedin.com/company/ezina-tech",
  x: "https://x.com/Ezina_AI",
  xHandle: "@Ezina_AI",
};

/** Where every "Talk to us" button and link goes (the contact page). */
export const contactHref = "/contact";

/**
 * Where every "Get Started" button goes (header, hero, audience cards, closing section).
 * null = the app is not ready: the button renders disabled with a "Coming soon" badge and links nowhere.
 * Set a URL (e.g. `${links.appUrl}${links.signupPath}`) and every Get Started becomes a normal link.
 */
export const getStartedUrl: string | null = null;

/** "Log in" in the header. null = hidden. Set to `${links.appUrl}${links.loginPath}` when the app is live. */
export const loginUrl: string | null = null;

export const getStarted = {
  label: "Get Started",
  comingSoon: "Coming soon",
};

// ---------------------------------------------------------------------------
// SEO
// ---------------------------------------------------------------------------

export const seo = {
  title: "Ezina | AI-Powered Agri Trade",
  description:
    "Ezina is the trust and intelligence infrastructure for agricultural trade: verified buyers and suppliers, real market intelligence and trusted connections for buyers, processors and institutions.",
  ogImage: "/og-image.png",
  ogImageAlt: "Ezina logo with the text: AI-Powered Agri Trade. Verified truth before you sell.",
  themeColor: "#0c1e34",
  locale: "en",
};

// ---------------------------------------------------------------------------
// Navigation, header, footer
// ---------------------------------------------------------------------------

export const nav = [
  { label: "For Buyers", href: "/#buyers" },
  { label: "For Partners", href: "/#partners" },
  { label: "How it works", href: "/#how-it-works" },
  { label: "Pricing", href: "/#pricing" },
  { label: "FAQ", href: "/#faq" },
  { label: "About", href: "/#about" },
];

export const header = {
  farmersLink: "Farmers: WhatsApp",
  login: "Log in",
  /** Header main action (replaces Get Started in the header; links to contactHref). */
  talkToUs: "Talk to us",
  /** Not shown in the header for now (the app is not ready); kept for when getStartedUrl is set. */
  getStarted: "Get Started",
  skipToContent: "Skip to main content",
  menu: "Menu",
};

export const floatingWhatsApp = {
  label: "Farmers: chat with Ezina on WhatsApp",
  short: "WhatsApp",
};

export const footer = {
  tagline: "Trust that can be verified.",
  footprint: "Validation footprint: Botswana · South Africa · Zambia",
  legal: [
    { label: "Privacy Policy", href: "/privacy" },
    { label: "Terms of Service", href: "/terms" },
  ],
  disclaimer:
    "Ezina is in validation and is not yet incorporated. Nothing on this site is an offer of a guaranteed sale, price or payment.",
  copyright: "© 2026 Ezina.",
};

// ---------------------------------------------------------------------------
// 1. Hero
// ---------------------------------------------------------------------------

export const hero = {
  eyebrow: "AI-Powered Agri Trade",
  /** Short form of "The trust and intelligence infrastructure for agricultural trade." The highlight is coloured. */
  headline: { before: "Trust and ", highlight: "intelligence", after: " for agricultural trade." },
  subtext: "Verified farmer supply, market intelligence and trusted connections for buyers, processors and institutions.",
  farmerLink: "Are you a farmer? Chat with Ezina on WhatsApp →",
  /**
   * Background photo (scene-setting only, not an Ezina farm). Free stock, Pexels licence:
   * https://www.pexels.com/photo/scenic-sunset-over-minnesota-cornfield-33443252/
   * Files are pre-cropped WebPs in public/images: 750 (tall, phones), 1280 and 1920 (wide).
   */
  photo: {
    alt: "Rows of young maize stretching to the hills at sunset",
    mobile: "/images/hero-field-750.webp",
    wide: "/images/hero-field-1280.webp",
    wide2x: "/images/hero-field-1920.webp",
  },
  /** Glass cards on the right of the hero (wording from the rest of the site). */
  cards: [
    { icon: "shield", title: "Verified buyers & suppliers", body: "Checked against evidence, not claims." },
    { icon: "track", title: "Market intelligence", body: "Price references with their sources stated." },
    { icon: "link", title: "Trusted connections", body: "Supply and demand matched into real opportunities." },
  ] as const,
};

/**
 * Key stats strip under the hero. Edit one line to update a number.
 * - display: the final text, always in the static HTML (what search engines, no-JS and reduced-motion visitors see).
 * - countTo: the number the count-up animates to before showing `display`; null = static text, no animation.
 * Figures confirmed by the owner on 2026-11-27.
 */
export type Stat = { display: string; countTo: number | null; label: string };

export const stats: Stat[] = [
  { display: "1K+", countTo: 1000, label: "Farmers Connected" },
  { display: "10+", countTo: 10, label: "Crop Varieties" },
  { display: "24/7", countTo: null, label: "AI-Powered" },
  { display: "3+", countTo: 3, label: "Countries" },
];
export const statsHeading = "Ezina in numbers";

// ---------------------------------------------------------------------------
// WhatsApp demo ("See how farmers use Ezina"). An example conversation, not a real transcript.
// ---------------------------------------------------------------------------

/**
 * One chat bubble. `text` supports WhatsApp formatting: *bold*, emoji and line breaks (\n).
 * `location` renders a shared-location bubble instead of text.
 * `buttons` adds WhatsApp-style quick-reply buttons under an Ezina message; `tap` is the button the animation
 * highlights as if the farmer tapped it (the farmer's reply bubble should follow).
 */
export type ChatMessage = {
  from: "farmer" | "ezina";
  time: string;
  text?: string;
  location?: string;
  buttons?: string[];
  tap?: string;
};

export type DemoCard = {
  icon: "check" | "price" | "warn" | "search";
  title: string;
  body: string;
  /** Index of the first step (0-based) at which the card is shown. */
  fromStep: number;
  /** Where it floats around the phone on desktop. */
  position: "top-left" | "top-right" | "mid-right" | "bottom-left";
};

export const demo = {
  eyebrow: "How farmers use Ezina",
  heading: "See how farmers use Ezina",
  intro:
    "Farmers meet Ezina on WhatsApp, where they already are. Every price question becomes structured, consented data, and that is where buyer intelligence starts.",
  /** Shown under the phone. The figures in this example are illustrative, not real market data. */
  label: "Example conversation · example figures",
  stepsLabel: "Steps of the example conversation",
  /**
   * Each step plays its own messages in the phone (the chat starts at the top for every step).
   * The static HTML shows the whole conversation, all steps in order.
   */
  steps: [
    {
      title: "Farmer asks a question",
      body: "“What is the price for tomatoes?”",
      messages: [{ from: "farmer", time: "09:02", text: "What is the current market price for tomatoes? 🍅" }],
    },
    {
      title: "Ezina gets the details",
      body: "Location, grade and quantity",
      messages: [
        {
          from: "ezina",
          time: "09:02",
          text: "I can help. To give you a useful price reference I need:\n1. Your location (📎 → Location)\n2. The grade of your tomatoes\n3. Roughly how much you have",
        },
        { from: "farmer", time: "09:04", location: "Kweneng" },
        { from: "farmer", time: "09:04", text: "Grade A, about 500 kg" },
      ],
    },
    {
      title: "Verified price reference",
      body: "Prices with sources and uncertainties",
      messages: [
        {
          from: "ezina",
          time: "09:05",
          text: "Grade A tomatoes near Kweneng: *P9.50–P11.00/kg* from 2 verified buyers this week.\n⚠️ Final price depends on quality checks.",
        },
      ],
    },
    {
      title: "Farmer chooses what's next",
      body: "Find a buyer, share supply or not now",
      messages: [
        {
          from: "ezina",
          time: "09:06",
          text: "What would you like to do next?",
          buttons: ["Find a verified buyer", "Share my supply", "Not now"],
          tap: "Find a verified buyer",
        },
        { from: "farmer", time: "09:06", text: "Find a verified buyer" },
        {
          from: "ezina",
          time: "09:06",
          text: "Great, I'll look for verified buyers who need Grade A tomatoes near Kweneng and send you the matches with their verification reports. 🔍",
        },
      ],
    },
  ] satisfies Array<{ title: string; body: string; messages: ChatMessage[] }>,
  /** Small floating cards around the phone (desktop and tablet), shown in sync with the steps. */
  cards: [
    { icon: "check", title: "Buyer verified", body: "Identity and registration confirmed", fromStep: 1, position: "top-left" },
    { icon: "price", title: "P9.50–P11.00/kg", body: "2 verified buyers · this week", fromStep: 2, position: "mid-right" },
    { icon: "warn", title: "Uncertain", body: "Final price depends on quality checks", fromStep: 2, position: "bottom-left" },
    { icon: "search", title: "Matching buyers", body: "Verified buyers only · reports included", fromStep: 3, position: "top-right" },
  ] satisfies DemoCard[],
};

// ---------------------------------------------------------------------------
// 2. Who it's for ("What is Ezina for?", wording from the original www.ezina.ai section)
// ---------------------------------------------------------------------------

export type AudienceCard = {
  /** Anchor id. The header nav links to #buyers and #partners. */
  id: string;
  icon: "sprout" | "crate" | "building" | "globe";
  title: string;
  /** Optional small badge next to the title. */
  badge?: string;
  /** Exactly 3 short points, taken from the original card sentence. */
  benefits: [string, string, string];
  /** Optional line under the points. */
  note?: string;
  /** Text link at the bottom of the card (no Get Started: the app isn't ready). */
  /**
   * `highlight`: id of a "How Ezina earns" card to pulse once when it comes into view after this link is used
   * (see components/PlanHighlighter.tsx).
   */
  cta: { label: string; href: string; external?: boolean; highlight?: string };
};

export const audiences = {
  eyebrow: "What is Ezina for?",
  heading: "Different needs. One platform. A stronger agricultural value chain.",
  cards: [
    {
      id: "farmers",
      icon: "sprout",
      title: "For farmers",
      badge: "Free",
      benefits: ["Verified opportunities", "Market price information", "Trusted buyers"],
      note: "The essential service is free.",
      cta: { label: "Chat on WhatsApp →", href: links.whatsappUrl, external: true },
    },
    {
      id: "buyers",
      icon: "crate",
      title: "For buyers",
      benefits: ["Verified farmer supply", "Market intelligence", "Sourcing services you can plan around"],
      cta: { label: "What buyers receive →", href: "/#what-buyers-receive" },
    },
    {
      id: "partners",
      icon: "building",
      title: "For institutions",
      benefits: ["Aggregated data", "Market insights", "Network access across the corridors you serve"],
      cta: { label: "See how it works for institutions →", href: "/#pricing", highlight: "institutions-plan" },
    },
    {
      id: "export-partners",
      icon: "globe",
      title: "Export partners",
      benefits: ["Reliable supply", "Managed export readiness", "Reduced risk before you commit"],
      // Exporters are served by the buyer offer (sourcing and verification services), so that card is highlighted.
      cta: { label: "See how it works for exporters →", href: "/#pricing", highlight: "buyers-plan" },
    },
  ] satisfies AudienceCard[],
};

// ---------------------------------------------------------------------------
// 3. How Ezina works
// ---------------------------------------------------------------------------

export const howItWorks = {
  eyebrow: "How Ezina works",
  heading: "Smarter information. Better decisions.",
  intro:
    "Ezina uses AI and verified evidence to give you reliable agricultural intelligence, from farm to market.",
  steps: [
    { icon: "chat", title: "Share your needs", body: "Tell us what you need, or check prices for a crop, grade and area." },
    { icon: "shield", title: "We verify", body: "Buyers and suppliers are checked against evidence, not claims." },
    { icon: "link", title: "Get matched", body: "Suitable supply and demand are matched into real opportunities." },
    { icon: "track", title: "Track progress", body: "Every opportunity is tracked, step by step, with outcomes recorded." },
  ] as const,
};

// ---------------------------------------------------------------------------
// 5. What buyers receive (examples from the original site)
// ---------------------------------------------------------------------------

export type Status = "confirmed" | "checked" | "limited" | "not-confirmed" | "review";

export const verifiedExample = {
  eyebrow: "For buyers",
  heading: "What buyers receive",
  intro: "Every opportunity comes with evidence: what was checked, what was confirmed, and what is still uncertain.",
  stepsLabel: "What buyers receive, step by step",
  /** The stepper on the right (desktop) / below the card (phones). Each step shows one card. */
  steps: [
    { title: "Buyer verification report", body: "Who the buyer is, and what was confirmed" },
    { title: "Verified opportunity", body: "The offer, with its status on each point" },
    { title: "Evidence & uncertainty", body: "What was checked, and what is still open" },
  ],
  /** Small floating note beside the card, one per step (decorative; the same facts are in the card). */
  floating: ["3 of 5 checks confirmed", "Price needs review", "Evidence attached to every claim"],
  report: {
    title: "Verification Report",
    badge: "Example only",
    buyerLabel: "Buyer",
    name: "ABC Fresh Produce Ltd",
    meta: "Produce buyer · Gaborone",
    rows: [
      { label: "Identity", value: "Confirmed", status: "confirmed" },
      { label: "Registration", value: "Confirmed", status: "confirmed" },
      { label: "References", value: "Checked", status: "checked" },
      { label: "Payment history", value: "Limited evidence", status: "limited" },
      { label: "Purchase capacity", value: "Not confirmed", status: "not-confirmed" },
    ] satisfies Array<{ label: string; value: string; status: Status }>,
    note: "Payment cannot guarantee a positive verification result. Reports reflect information available at the time.",
  },
  opportunity: {
    label: "Verified opportunity",
    badge: "Not a live offer",
    name: "Fresh Tomatoes Available",
    facts: [
      { label: "Quantity", value: "2,000 kg" },
      { label: "Location", value: "Kweneng" },
      { label: "Buyer identity", value: "Confirmed", status: "confirmed" },
      { label: "Offer assessment", value: "Price needs review", status: "review" },
    ] satisfies Array<{ label: string; value: string; status?: Status }>,
  },
  evidence: {
    label: "Evidence & uncertainty",
    title: "Fresh Tomatoes Available",
    checkedTitle: "Checked",
    checked: [
      "Business identity and registration",
      "Buyer purchasing requirements",
      "Available farmer supply",
      "Relevant market price references",
    ],
    uncertainTitle: "Uncertain",
    uncertain: ["Final quality inspection", "Delivery arrangements", "Payment confirmation"],
    note: "Verification does not guarantee a sale, price or payment.",
  },
};

// ---------------------------------------------------------------------------
// 6. Validation story
// ---------------------------------------------------------------------------

/**
 * Validation story: an ILLUSTRATIVE scenario (maize, Kenya) with example figures, labelled as such on the page.
 * It shows how Ezina works; it is not a record of a completed transaction. No real person or company is named.
 * The real validation evidence is the `evidence` line below the stepper.
 */
export const validationStory = {
  eyebrow: "Validation story",
  heading: "From a Farmer's Need to a Verified Opportunity",
  badge: "Illustrative scenario · example figures",
  intro: "One farmer's sale, step by step: from a low broker offer to a verified buyer, with the problems stated plainly.",
  stepsLabel: "Validation story, step by step",
  steps: [
    { title: "The Challenge", body: "A low broker offer, and no way to check" },
    { title: "What Ezina Did", body: "Prices, buyer checks, requirements, match" },
    { title: "The Outcome", body: "A better price, with the challenges stated" },
  ],
  challenge: {
    kicker: "The Challenge",
    farmer: "A smallholder maize farmer in Trans Nzoia, Kenya",
    location: "📍 Trans Nzoia, Kenya",
    crop: "🌽 Dry maize · ~50 bags",
    cropDetail: "90 kg bags, roughly 4.5 tonnes",
    problemsTitle: "The problem",
    problems: [
      "Brokers at the farm gate were offering a low price.",
      "There was no way to check current market prices.",
      "No way to know which buyers were genuine, or would pay on time.",
    ],
    brokerTag: "Broker offer: KES 2,800/bag",
  },
  did: {
    kicker: "What Ezina Did",
    title: "Four checks before any commitment",
    actions: [
      {
        icon: "price",
        title: "Price references",
        body: "Current references for dry maize near Eldoret: KES 3,200–3,500 per 90 kg bag, with sources and dates, compared with the broker's farm-gate offer of KES 2,800.",
      },
      {
        icon: "shield",
        title: "Buyer verification",
        body: "A registered maize miller in Eldoret: identity and registration confirmed, references checked.",
        chip: "Payment history: limited evidence",
      },
      {
        icon: "list",
        title: "Requirements check",
        body: "Moisture at or below 13.5%, clean grain, delivery to the mill.",
      },
      {
        icon: "link",
        title: "Matching",
        body: "The farmer's supply matched to the buyer's requirement; the verification report shared with the farmer before any commitment.",
      },
    ] as Array<{ icon: "price" | "shield" | "list" | "link"; title: string; body: string; chip?: string }>,
  },
  outcome: {
    kicker: "The Outcome",
    title: "Matched with a verified buyer",
    compareTitle: "Price per 90 kg bag",
    bars: [
      { label: "Broker offer", value: 2800, display: "KES 2,800" },
      { label: "Matched reference price", value: 3300, display: "KES 3,300" },
    ],
    notes: [
      {
        label: "Challenge",
        text: "The first moisture test came in above the limit, so the farmer dried the maize for two more days before delivery.",
      },
      {
        label: "Uncertainty",
        text: "The farmer paid for transport to the mill, which reduced the net gain. Payment arrived after 10 days, not on delivery.",
      },
    ],
    recorded: "Recorded for future matches",
    recordedBody: "Every step was logged: what was verified, what was uncertain, and what happened.",
  },
  note: "This scenario shows how Ezina works. It is not a record of a completed transaction.",
  /** Real validation evidence, stated plainly (not illustrative). */
  evidence:
    "Early validation: 24 farmers (4 in-depth interviews in Botswana and South Africa, 20 questionnaires in Sinda, Zambia).",
};

// ---------------------------------------------------------------------------
// 7. How Ezina earns
// ---------------------------------------------------------------------------

/** "Why choose Ezina" (titles from the original www.ezina.ai section; one-line descriptions from the site's own copy). */
export const whyChoose = {
  eyebrow: "Why choose Ezina",
  heading: "Why choose Ezina?",
  // The original intro opens with "More than a marketplace." — left out, because Ezina is not a marketplace.
  intro: "Ezina is the intelligence layer that makes agricultural trade more trustworthy, efficient and profitable.",
  items: [
    { icon: "shield", title: "Trusted verification", body: "Buyers and suppliers checked against evidence, not claims." },
    { icon: "chart", title: "Real market intelligence", body: "Price references and supply data, with their sources stated." },
    { icon: "link", title: "Strong connections", body: "Verified buyers matched with real farmer supply." },
    { icon: "risk", title: "Reduced risk", body: "See what is confirmed and what is uncertain before you commit." },
    { icon: "spark", title: "Greater opportunities", body: "Reach farmer supply across the corridors you serve." },
  ] as Array<{ icon: "shield" | "chart" | "link" | "risk" | "spark"; title: string; body: string }>,
};

/** "How Ezina earns" (wording from the original www.ezina.ai section). Pricing-style, with no prices. */
export const earns = {
  id: "pricing",
  eyebrow: "How Ezina earns",
  heading: "Farmers build the network. Buyers create demand. Institutions create scale.",
  intro: "Ezina provides the intelligence that connects them, and the revenue follows the value.",
  cards: [
    {
      id: "buyers-plan",
      audience: "Buyers",
      title: "Buyers pay for intelligence",
      /** Emphasised card (buyers are the main audience). */
      highlight: "For buyers",
      items: [
        "Intelligence subscriptions: verified supply, crop availability, harvest dates and market insight",
        "Verification reports on the businesses they trade with",
        "Procurement and sourcing services",
        "A grading fee, paid by the buyer, never the farmer",
      ],
      cta: { label: "Talk to us", href: contactHref },
    },
    {
      id: "institutions-plan",
      audience: "Institutions",
      title: "Institutions pay for scale",
      items: [
        "Annual contracts for agricultural intelligence",
        "Supply mapping and farmer network monitoring",
        "Market research and programme reporting",
        "Licensing for the farmer networks they support",
      ],
      cta: { label: "Talk to us", href: contactHref },
    },
    {
      id: "farmers-plan",
      audience: "Farmers",
      title: "Farmers start free",
      badge: "Free",
      items: [
        "Essential access is free: verified opportunities, price information, buyer summaries",
        "Optional paid services, per service: advanced market reports",
        "Export readiness support, paid per service",
      ],
      cta: { label: "Chat on WhatsApp", href: links.whatsappUrl, external: true },
    },
  ] as Array<{
    id: string;
    audience: string;
    title: string;
    highlight?: string;
    badge?: string;
    items: string[];
    cta: { label: string; href: string; external?: boolean };
  }>,
  statements: [
    { icon: "nocut", text: "Ezina does not move money or take a cut of farmer sales." },
    { icon: "chat", text: "Buyer and institution pricing is being validated. Talk to us for details." },
  ] as Array<{ icon: "nocut" | "chat"; text: string }>,
};

// ---------------------------------------------------------------------------
// 8. FAQ (answers drawn from the original site)
// ---------------------------------------------------------------------------

export const faq = {
  eyebrow: "FAQ",
  heading: "Questions buyers and partners ask",
  items: [
    {
      q: "How does Ezina verify suppliers and buyers?",
      a: [
        "Ezina uses AI and verified evidence to check buyers and suppliers, not their claims. Each report states what was confirmed (for example identity and registration), what was checked (for example references), and what has limited evidence or is not confirmed (for example payment history or purchasing capacity).",
        "Verification is independent: payment never buys a positive result. A report shows the information available at the time of verification, and verified never means a guaranteed sale, price or payment.",
      ],
    },
    {
      q: "What do buyers get with a subscription?",
      a: [
        "An intelligence subscription gives buyers verified supply, crop availability, harvest dates and market insight. Buyers can also order verification reports on the businesses they trade with, and procurement and sourcing services.",
        "Pricing is being validated through real customer conversations and will be published when it is proven. Talk to us at hello@ezina.ai.",
      ],
    },
    {
      q: "Which countries and crops does Ezina cover?",
      a: [
        "Ezina is in validation with farmers in Botswana, South Africa and Zambia. Kenya and India have been identified as expansion markets.",
        "More than 10 crop varieties are covered so far. [TODO: list the main crops]",
      ],
    },
    {
      q: "How is farmer data protected?",
      a: [
        "Farmers share information with Ezina through WhatsApp, with their consent. They can see, correct, update or delete their information, and choose how Ezina may contact them.",
        "Farmer information is never sold or shared without the farmer's permission. Buyers see only the information a farmer has agreed to share. Confirmed facts are kept separate from estimates and assumptions.",
      ],
    },
    {
      q: "Is Ezina free for farmers?",
      a: [
        "Yes. Essential access is free: verified opportunities, price information and buyer summaries. Optional services, such as advanced market reports and export readiness support, are paid per service. Grading fees are paid by the buyer, never the farmer.",
        "Ezina moves no money and takes no cut of a farmer's sale.",
      ],
    },
  ],
};

// ---------------------------------------------------------------------------
// 9. Founders
// ---------------------------------------------------------------------------

export const founders = {
  eyebrow: "About",
  heading: "The founders",
  intro: "Built across Botswana, Kenya and India, by a team that combines agriculture, trade, technology and growth.",
  people: [
    {
      name: "Alakanani Itireleng",
      role: "Founder",
      photo: "/images/founder-alakanani",
      bio: "Leads Ezina's vision, strategy and strategic partnerships. A Botswana-born educator and technology entrepreneur, she taught for more than a decade before moving into technology in 2014, founding SatoshiCentre and the SwiftRun delivery platform. Her work on Ezina starts with listening to farmers.",
      linkedin: "[TODO: LinkedIn URL]",
    },
    {
      name: "Chitta Ranjan Behera",
      role: "Co-founder, Engineering",
      photo: "/images/founder-chitta",
      bio: "Leads engineering, product architecture and technical strategy from Bengaluru, India. A technology and AI leader with over 20 years of experience, most recently Senior Architect at Brillio, he has built enterprise platforms, multi-agent systems and intelligent automation.",
      linkedin: "[TODO: LinkedIn URL]",
    },
    {
      name: "Frank Deya",
      role: "Co-founder, Growth",
      photo: "/images/founder-frank",
      bio: "Leads growth, commercial strategy and partnerships from Nairobi, Kenya. He has more than eight years of experience building markets across Africa, including expansion across eight markets as Director for Africa at Coin Gaming Network, and Gates Foundation funding as COO of Bitsoko.",
      linkedin: "[TODO: LinkedIn URL]",
    },
  ],
};

// ---------------------------------------------------------------------------
// 10. Closing CTA
// ---------------------------------------------------------------------------

export const closing = {
  heading: "Let's grow a more connected agricultural future.",
  body: "Ezina is in validation with farmers across Botswana, South Africa and Zambia, and is opening conversations with buyers, processors and institutions.",
  talkToUs: "Talk to us →",
  farmerLink: "Are you a farmer? Chat with Ezina on WhatsApp →",
};

// ---------------------------------------------------------------------------
// Contact page (/contact, "Talk to us")
// ---------------------------------------------------------------------------

export const contactPage = {
  title: "Talk to us | Ezina",
  description:
    "Talk to Ezina about verified farmer supply, market intelligence or a partnership. Tell us what you need and our team will get back to you.",
  eyebrow: "Contact",
  heading: "Talk to us",
  intro: "Want verified supply, market intelligence or a partnership? Tell us what you need and our team will get back to you.",
  fields: {
    firstName: { label: "First name", placeholder: "First name" },
    lastName: { label: "Last name", placeholder: "Last name" },
    email: { label: "Work email", placeholder: "name@company.com" },
    phone: { label: "Phone number", placeholder: "+267 71 234 567", optional: "Optional" },
    company: { label: "Company", placeholder: "Company or organisation" },
    message: { label: "Message", placeholder: "What do you need? Crops, volumes, regions, timing, or the partnership you have in mind." },
  },
  messageMin: 20,
  messageMax: 2000,
  errors: {
    required: "This field is required.",
    email: "Enter a valid email address, like name@company.com.",
    phone: "Enter a valid phone number (digits, spaces, + and - only).",
    messageMin: "Please write at least 20 characters.",
    messageMax: "Please keep your message under 2,000 characters.",
    summary: "Please check the highlighted fields.",
    generic: "Something went wrong. Please try again or email hello@ezina.ai.",
  },
  submit: "Send message",
  sending: "Sending…",
  success: {
    label: "Complete",
    heading: "Thank you! We’ll be in touch shortly.",
    again: "Send another message",
  },
  privacyNote: "We use these details only to reply to you.",
  privacyLink: "Privacy policy",
  aside: {
    heading: "Other ways to reach us",
    emailLabel: "Email",
    farmers: "Farmers: chat with Ezina on WhatsApp →",
    socialLabel: "Follow Ezina",
    whereLabel: "Where we work",
    // [TODO: confirm the cities where Ezina works] (no street addresses yet)
    where: "Gaborone, Botswana · Bengaluru, India · Nairobi, Kenya",
  },
};

// ---------------------------------------------------------------------------
// Legal pages (drafts pending legal review)
// ---------------------------------------------------------------------------

export type LegalSection = { heading: string; paragraphs?: string[]; items?: string[] };

export const legal = {
  draftNotice:
    "Draft pending legal review. This page is a working draft, not final legal text. Questions: hello@ezina.ai.",
  entityName: "[TODO: legal entity name]",
  address: "[TODO: registered address]",
  governingLaw: "[TODO: governing law and jurisdiction]",
  lastUpdated: "[TODO: date of final version]",
  privacy: {
    title: "Privacy Policy",
    description: "How Ezina collects, uses and protects personal information shared through WhatsApp and this website.",
    sections: [
      {
        heading: "Who we are",
        paragraphs: [
          "This policy explains how Ezina (\"Ezina\", \"we\", \"us\") collects, uses and protects personal information shared through our WhatsApp service and this website (www.ezina.ai).",
          "Ezina is in validation and is not yet incorporated. Operator: [TODO: legal entity name], [TODO: registered address].",
        ],
      },
      {
        heading: "Information we collect from farmers",
        paragraphs: ["Farmers share information with Ezina through WhatsApp, with their consent. This can include:"],
        items: [
          "Name and WhatsApp phone number",
          "Farm, crop and supply details the farmer chooses to share, such as crops, quantities, grades and harvest timing",
          "Location, only when the farmer shares a WhatsApp location pin. We never ask farmers to type GPS coordinates",
          "Photos, voice notes and documents the farmer chooses to send",
          "The messages exchanged with Ezina",
        ],
      },
      {
        heading: "Information from buyers, partners and website visitors",
        paragraphs: [
          "If you contact us through the contact form or by email, we collect what you send: your name, work email, company, message and, if you give it, your phone number. We use it only to reply to you.",
          "This website does not use advertising cookies or tracking scripts. [TODO: update this section if analytics are added]",
        ],
      },
      {
        heading: "Consent",
        paragraphs: [
          "We ask farmers for their consent on WhatsApp before we save their profile. Farmers can withdraw consent at any time by messaging Ezina or emailing hello@ezina.ai.",
        ],
      },
      {
        heading: "How we use information",
        items: [
          "To give farmers price information and tell them about verified opportunities",
          "To verify buyers and suppliers, and match supply and demand, with the farmer's permission",
          "To reply to enquiries",
          "To run, secure and improve the service",
          "To produce aggregated statistics that do not identify any individual farmer",
        ],
      },
      {
        heading: "Who can see it",
        items: [
          "Ezina does not sell personal information.",
          "Farmer information is never shared without the farmer's permission. Buyers see only the farmer information the farmer has agreed to share.",
          "Service providers that run parts of the service for us, such as the WhatsApp Business Platform (Meta), cloud hosting and database providers, and an AI language provider that helps us understand messages, process information only on our instructions. [TODO: confirm the list of service providers]",
          "We may disclose information where the law requires it.",
        ],
      },
      {
        heading: "Your choices and rights",
        paragraphs: [
          "Farmers can see, correct, update or delete their information, and choose how Ezina may contact them. To do this, message Ezina on WhatsApp or email hello@ezina.ai. Buyers, partners and visitors can make the same requests by email.",
        ],
      },
      {
        heading: "How long we keep information",
        paragraphs: ["[TODO: retention periods for farmer profiles, conversations and enquiries]"],
      },
      {
        heading: "Security",
        paragraphs: [
          "We use reasonable technical and organisational measures to protect information, such as access controls and encrypted connections. No system is completely secure.",
        ],
      },
      {
        heading: "International transfers",
        paragraphs: [
          "Our service providers may process information outside the country where it was collected. [TODO: describe where data is processed and the safeguards used]",
        ],
      },
      {
        heading: "Children",
        paragraphs: ["Ezina is not intended for children. [TODO: confirm minimum age]"],
      },
      {
        heading: "Changes to this policy",
        paragraphs: [
          "We will update this page when our practices change, and tell farmers on WhatsApp about important changes.",
        ],
      },
    ] satisfies LegalSection[],
  },
  terms: {
    title: "Terms of Service",
    description: "The terms for using Ezina's WhatsApp service and website.",
    sections: [
      {
        heading: "About these terms",
        paragraphs: [
          "These terms apply to your use of Ezina's WhatsApp service and this website. By using Ezina you agree to them.",
          "Ezina is in validation and is not yet incorporated. Operator: [TODO: legal entity name], [TODO: registered address].",
        ],
      },
      {
        heading: "What Ezina is, and is not",
        paragraphs: [
          "Ezina is a trust and intelligence service for agricultural trade. It verifies buyers and suppliers, provides market price information and connects farmers with verified opportunities.",
          "Ezina is not a marketplace and is not a party to any sale. Ezina does not move money, hold funds or take a cut of farmer sales. Any agreement to buy or sell is made directly between the buyer and the seller.",
        ],
      },
      {
        heading: "No guarantee of sale, price or payment",
        items: [
          "Verification shows the information available at the time of verification. \"Verified\" never means a guaranteed sale, price or payment.",
          "Price references are references, not offers.",
          "Quality, delivery and payment are arranged between the buyer and the seller. Each party remains responsible for its own checks and decisions.",
        ],
      },
      {
        heading: "Independent verification",
        paragraphs: ["No one can pay for a better verification result. Paying for a report never guarantees a positive outcome."],
      },
      {
        heading: "Your responsibilities",
        items: [
          "Give accurate information, and update it when it changes",
          "Use Ezina lawfully, and do not misrepresent yourself, your business or your produce",
          "Do not misuse the service, for example by sending spam or trying to access other people's information",
        ],
      },
      {
        heading: "Fees",
        paragraphs: [
          "Essential access is free for farmers. Paid services for buyers and institutions, and optional paid services for farmers, are agreed separately before any charge. [TODO: pricing and payment terms]",
        ],
      },
      {
        heading: "Your information",
        paragraphs: ["How we handle personal information is described in our Privacy Policy at www.ezina.ai/privacy."],
      },
      {
        heading: "Service changes",
        paragraphs: ["Ezina is in validation. Features may change, pause or stop while we learn what works."],
      },
      {
        heading: "Limitation of liability",
        paragraphs: [
          "To the extent permitted by law, Ezina is not liable for the outcome of any trade between users, or for decisions made using information from Ezina. [TODO: final wording after legal review]",
        ],
      },
      {
        heading: "Governing law",
        paragraphs: ["[TODO: governing law and jurisdiction]"],
      },
    ] satisfies LegalSection[],
  },
};

/** True if a value is still a placeholder. */
export const isTodo = (value: string) => value.includes("[TODO");
