import type { PlatformAdapter } from "./index";

/**
 * Lever posts native inputs named `name`, `email`, `phone`, `org`, and
 * `urls[LinkedIn]` / `urls[GitHub]`. Specific hints come first so `email` /
 * `org` win before the generic `name` → fullName fallback.
 */
export const leverAdapter: PlatformAdapter = {
  id: "lever",
  fieldHints: [
    { match: "email", key: "email" },
    { match: "phone", key: "phone" },
    { match: "linkedin", key: "linkedin" },
    { match: "github", key: "github" },
    { match: "org", key: "currentCompany" },
    { match: "resume", key: "resumeFile" },
    { match: "name", key: "fullName" },
  ],
  submitSelectors: [
    "button[type='submit']",
    ".template-btn-submit",
    "button.postings-btn",
  ],
};
