import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";
import { legal } from "@/content/site";
import { pageMetadata } from "@/lib/metadata";

const { title, description, sections } = legal.terms;

export const metadata: Metadata = pageMetadata({ path: "/terms", title: `${title} | Ezina`, description });

export default function TermsPage() {
  return <LegalPage title={title} sections={sections} />;
}
