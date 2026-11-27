import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Inter, Libre_Franklin } from "next/font/google";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { JsonLd } from "@/components/JsonLd";
import { footer, links, seo, siteUrl } from "@/content/site";
import { pageMetadata } from "@/lib/metadata";
import "./globals.css";

// Self-hosted at build time by next/font: no runtime request to Google.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const franklin = Libre_Franklin({
  subsets: ["latin"],
  variable: "--font-franklin",
  display: "swap",
  weight: ["600", "700", "800"],
});

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  ...pageMetadata({ path: "/", title: seo.title }),
};

export const viewport: Viewport = {
  themeColor: seo.themeColor,
  width: "device-width",
  initialScale: 1,
};

const organization = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "Ezina",
  url: siteUrl,
  logo: `${siteUrl}/logo.png`,
  description: seo.description,
  slogan: footer.tagline,
  email: links.email,
  sameAs: [links.linkedin, links.x],
  areaServed: ["Botswana", "South Africa", "Zambia"],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang={seo.locale} className={`${inter.variable} ${franklin.variable}`}>
      <body>
        <JsonLd data={organization} />
        <Header />
        <main id="main">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
