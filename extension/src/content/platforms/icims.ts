import type { PlatformAdapter } from "./index";

/**
 * iCIMS renders inside iframes with generated ids. Hints are conservative
 * (substrings that appear in iCIMS field ids/names); the generic label mapper
 * carries most of the load. Multi-page, so provide next/submit selectors.
 */
export const icimsAdapter: PlatformAdapter = {
  id: "icims",
  fieldHints: [
    { match: "firstname", key: "firstName" },
    { match: "lastname", key: "lastName" },
    { match: "email", key: "email" },
    { match: "phone", key: "phone" },
    { match: "addressstreet", key: "addressLine1" },
    { match: "addresscity", key: "city" },
    { match: "addresszip", key: "postalCode" },
  ],
  nextSelectors: [
    ".iCIMS_NextButton",
    "a[title='Next']",
    "button[name*='next']",
  ],
  submitSelectors: [
    ".iCIMS_SubmitButton",
    "input[type='submit']",
    "button[type='submit']",
  ],
};
