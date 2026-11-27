import { DemoShowcase } from "./DemoShowcase";

/**
 * "See how farmers use Ezina": one phone + interactive steps (see DemoShowcase).
 * The section fills one screen below the 72px sticky header (svh handles mobile browser bars) and centres its content.
 */
export function WhatsAppDemo() {
  return (
    <section
      aria-labelledby="demo-heading"
      className="relative flex min-h-[calc(100svh-72px)] items-center overflow-hidden py-4 sm:py-6 lg:py-7"
    >
      <div className="container-page">
        <DemoShowcase />
      </div>
    </section>
  );
}
