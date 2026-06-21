import { describe, it, expect } from "vitest";
import { renderTemplate, DEFAULT_TEMPLATES } from "./templates";

describe("renderTemplate", () => {
  it("substitutes known placeholders", () => {
    const out = renderTemplate("Hi {firstName} at {company}, — {myName}", {
      firstName: "Ada",
      company: "Acme",
      myName: "Sam",
    });
    expect(out).toBe("Hi Ada at Acme, — Sam");
  });

  it("collapses cleanly when placeholders are empty", () => {
    const out = renderTemplate("Hi {firstName}, I saw {company}.", { firstName: "Ada" });
    expect(out).toBe("Hi Ada, I saw .");
    expect(out).not.toContain("{");
  });

  it("default templates reference the standard placeholders", () => {
    const referral = DEFAULT_TEMPLATES.find((t) => t.id === "referral_ask")!;
    expect(referral.body).toContain("{role}");
    expect(referral.body).toContain("{company}");
  });
});
