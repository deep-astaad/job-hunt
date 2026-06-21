import type { PlatformAdapter } from "./index";

/**
 * Ashby is a React SPA. System fields carry ids like `_systemfield_name` /
 * `_systemfield_email`. Often single-page, but supports stepped forms — provide
 * next/submit selectors for the flow runner.
 */
export const ashbyAdapter: PlatformAdapter = {
  id: "ashby",
  fieldHints: [
    { match: "_systemfield_email", key: "email" },
    { match: "_systemfield_phone", key: "phone" },
    { match: "_systemfield_name", key: "fullName" },
    { match: "email", key: "email" },
    { match: "phone", key: "phone" },
    { match: "linkedin", key: "linkedin" },
    { match: "github", key: "github" },
    { match: "resume", key: "resumeFile" },
  ],
  nextSelectors: [
    "button[type='button']._continue_",
    "button[aria-label*='Continue']",
  ],
  submitSelectors: [
    "button[type='submit']",
    "button[aria-label*='Submit']",
  ],
};
