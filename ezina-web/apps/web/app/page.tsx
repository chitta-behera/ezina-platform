import { Hero } from "@/components/home/Hero";
import { Audiences } from "@/components/home/Audiences";
import { HowItWorks } from "@/components/home/HowItWorks";
import { WhatsAppDemo } from "@/components/home/WhatsAppDemo";
import { VerifiedExample } from "@/components/home/VerifiedExample";
import { ValidationStory } from "@/components/home/ValidationStory";
import { WhyChoose } from "@/components/home/WhyChoose";
import { Earns } from "@/components/home/Earns";
import { Faq } from "@/components/home/Faq";
import { Founders } from "@/components/home/Founders";
import { Closing } from "@/components/home/Closing";

export default function HomePage() {
  return (
    <>
      <Hero />
      <Audiences />
      <HowItWorks />
      <WhatsAppDemo />
      <VerifiedExample />
      <ValidationStory />
      <WhyChoose />
      <Earns />
      <Faq />
      <Founders />
      <Closing />
    </>
  );
}
