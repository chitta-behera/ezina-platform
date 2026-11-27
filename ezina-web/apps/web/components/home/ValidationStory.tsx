import { StoryShowcase } from "./StoryShowcase";

/**
 * Validation story: a labelled illustrative scenario as a stepper (card on the right), plus the real validation
 * evidence line. Fills one screen below the 72px sticky header and centres its content.
 */
export function ValidationStory() {
  return (
    <section
      id="validation-story"
      aria-labelledby="story-heading"
      className="relative flex min-h-[calc(100svh-72px)] items-center overflow-hidden py-6 sm:py-10 lg:py-12"
    >
      <div className="container-page">
        <StoryShowcase />
      </div>
    </section>
  );
}
