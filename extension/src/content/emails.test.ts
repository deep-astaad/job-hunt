import { describe, it, expect } from "vitest";
import { extractEmails, pickBestEmail, parseSubjectBody } from "./emails";

describe("extractEmails", () => {
  it("extracts unique emails and drops noreply/example", () => {
    const out = extractEmails(
      "Reach us at careers@acme.com or jobs@acme.com. Ignore noreply@acme.com and a@example.com."
    );
    expect(out).toContain("careers@acme.com");
    expect(out).toContain("jobs@acme.com");
    expect(out).not.toContain("noreply@acme.com");
    expect(out).not.toContain("a@example.com");
  });

  it("de-dupes case-insensitively", () => {
    expect(extractEmails("HI@x.com hi@x.com")).toEqual(["hi@x.com"]);
  });
});

describe("pickBestEmail", () => {
  it("prefers careers/jobs/hr-style inboxes", () => {
    expect(pickBestEmail(["info@acme.com", "careers@acme.com"])).toBe("careers@acme.com");
    expect(pickBestEmail(["sales@acme.com", "hr@acme.com"])).toBe("hr@acme.com");
  });

  it("returns the first when none are preferred, undefined when empty", () => {
    expect(pickBestEmail(["info@acme.com", "sales@acme.com"])).toBe("info@acme.com");
    expect(pickBestEmail([])).toBeUndefined();
  });
});

describe("parseSubjectBody", () => {
  it("splits a 'Subject: …' reply", () => {
    const r = parseSubjectBody("Subject: Backend role\n\nHi team, I'd love to apply.");
    expect(r.subject).toBe("Backend role");
    expect(r.body).toBe("Hi team, I'd love to apply.");
  });

  it("treats the whole text as body when no subject line", () => {
    const r = parseSubjectBody("Hi team, no subject here.");
    expect(r.subject).toBe("");
    expect(r.body).toBe("Hi team, no subject here.");
  });
});
