import type { PlatformAdapter } from "./index";

/**
 * SmartRecruiters application forms use camelCase field ids (firstName,
 * lastName, email, phoneNumber) and a stepped layout.
 */
export const smartRecruitersAdapter: PlatformAdapter = {
  id: "smartrecruiters",
  fieldHints: [
    { match: "firstname", key: "firstName" },
    { match: "lastname", key: "lastName" },
    { match: "email", key: "email" },
    { match: "phone", key: "phone" },
    { match: "linkedin", key: "linkedin" },
    { match: "resume", key: "resumeFile" },
  ],
  nextSelectors: [
    "button[data-test='next-button']",
    "button[aria-label*='Next']",
  ],
  submitSelectors: [
    "button[data-test='submit-button']",
    "button[type='submit']",
  ],
};
