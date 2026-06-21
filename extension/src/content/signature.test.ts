import { describe, it, expect } from "vitest";
import { normalizeText, computeSignature } from "./signature";

describe("normalizeText", () => {
  it("lowercases and strips punctuation", () => {
    expect(normalizeText("First Name *")).toBe("first name");
  });

  it("removes volatile numeric and uuid fragments", () => {
    expect(normalizeText("question_12345 input")).toBe("question input");
    expect(normalizeText("field_a1b2c3d4e5f6 label")).toBe("field label");
  });

  it("handles undefined", () => {
    expect(normalizeText(undefined)).toBe("");
  });
});

describe("computeSignature", () => {
  it("is stable across volatile name attributes when label is the same", () => {
    const a = computeSignature({
      label: "Phone",
      name: "phone--input--98213",
      kind: "tel",
    });
    const b = computeSignature({
      label: "Phone",
      name: "phone--input--40021",
      kind: "tel",
    });
    expect(a).toBe(b);
  });

  it("buckets equivalent input kinds together", () => {
    const asText = computeSignature({ label: "Email", kind: "text" });
    const asEmail = computeSignature({ label: "Email", kind: "email" });
    expect(asText).toBe(asEmail);
  });

  it("distinguishes a text country field from a select country field", () => {
    const text = computeSignature({ label: "Country", kind: "text" });
    const select = computeSignature({ label: "Country", kind: "select" });
    expect(text).not.toBe(select);
  });

  it("falls back to name/id when no label", () => {
    const sig = computeSignature({ name: "linkedin_url", kind: "url" });
    expect(sig).toContain("linkedin url");
  });
});
