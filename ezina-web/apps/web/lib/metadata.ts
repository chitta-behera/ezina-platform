import type { Metadata } from "next";
import { links, seo } from "@/content/site";

const ogImage = { url: seo.ogImage, width: 1200, height: 630, alt: seo.ogImageAlt, type: "image/png" };

/**
 * Full metadata for a page. Next replaces (does not merge) openGraph/twitter objects in child
 * segments, so every page builds the complete set here.
 */
export function pageMetadata({
  path,
  title,
  description = seo.description,
}: {
  path: string;
  /** Full title as shown in the tab and in previews. */
  title: string;
  description?: string;
}): Metadata {
  return {
    title: { absolute: title },
    description,
    alternates: { canonical: path },
    openGraph: {
      type: "website",
      url: path,
      siteName: "Ezina",
      locale: "en",
      title,
      description,
      images: [ogImage],
    },
    twitter: {
      card: "summary_large_image",
      site: links.xHandle,
      title,
      description,
      images: [{ url: seo.ogImage, alt: seo.ogImageAlt }],
    },
  };
}
