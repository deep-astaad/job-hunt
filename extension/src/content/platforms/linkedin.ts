import type { PlatformAdapter } from "./index";

/**
 * LinkedIn "Easy Apply" is a multi-step modal. Fields are dynamic and usually
 * well-labeled (handled by the generic mapper), so the adapter's value is the
 * flow navigation: Next / Review / Submit live as aria-labelled buttons.
 */
export const linkedinAdapter: PlatformAdapter = {
  id: "linkedin",
  nextSelectors: [
    "button[aria-label='Continue to next step']",
    "button[aria-label='Review your application']",
    "footer button[aria-label*='next']",
  ],
  submitSelectors: [
    "button[aria-label='Submit application']",
    "button[aria-label*='Submit']",
  ],
};
