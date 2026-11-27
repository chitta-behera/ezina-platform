import { BuyersShowcase } from "./BuyersShowcase";

/**
 * "What buyers receive": stepper with one card (report → opportunity → evidence), mirroring the WhatsApp demo.
 * Fills one screen below the 72px sticky header and centres its content.
 */
export function VerifiedExample() {
  return (
    <section
      id="what-buyers-receive"
      aria-labelledby="receive-heading"
      className="relative flex min-h-[calc(100svh-72px)] items-center overflow-hidden border-y border-line bg-[#f7f3ea] py-6 sm:py-10 lg:py-12"
    >
      <div className="container-page">
        <BuyersShowcase />
      </div>
    </section>
  );
}
