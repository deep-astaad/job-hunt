import type { PlatformAdapter } from "./index";

/**
 * Greenhouse uses native inputs with stable ids/names like `first_name`,
 * `last_name`, `email`, `phone`, and a `resume` upload. Mostly single-page, so
 * the generic filler handles widgets; we add field hints + submit selector.
 */
export const greenhouseAdapter: PlatformAdapter = {
  id: "greenhouse",
  fieldHints: [
    { match: "first_name", key: "firstName" },
    { match: "last_name", key: "lastName" },
    { match: "email", key: "email" },
    { match: "phone", key: "phone" },
    { match: "linkedin", key: "linkedin" },
    { match: "website", key: "website" },
    { match: "resume", key: "resumeFile" },
  ],
  nextSelectors: ["button#next", "button[data-source='next']"],
  submitSelectors: [
    "#submit_app_button",
    "input[type='submit']",
    "button[type='submit']",
  ],
};
