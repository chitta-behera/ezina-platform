import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";
import { legal } from "@/content/site";
import { pageMetadata } from "@/lib/metadata";

const { title, description, sections } = legal.privacy;

export const metadata: Metadata = pageMetadata({ path: "/privacy", title: `${title} | Ezina`, description });

export default function PrivacyPage() {
  return <LegalPage title={title} sections={sections} />;
}
