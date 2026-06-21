import { describe, it, expect } from "vitest";
import { collectIssues, parseRequiredYears, type ValField } from "./validate";
import { emptyProfile, type CandidateProfile } from "@/profile/schema";

function profile(over: Partial<CandidateProfile> = {}): CandidateProfile {
  return { ...emptyProfile(), contact: { phone: "123", email: "a@b.io" }, ...over };
}

describe("parseRequiredYears", () => {
  it("extracts a required-years number from JD text", () => {
    expect(parseRequiredYears("5+ years of experience required")).toBe(5);
    expect(parseRequiredYears("at least 3 yrs in backend")).toBe(3);
    expect(parseRequiredYears("no number here")).toBeUndefined();
  });
});

describe("collectIssues", () => {
  it("flags empty required fields as errors", () => {
    const fields: ValField[] = [
      { id: "1", label: "First name", required: true, value: "" },
    ];
    const issues = collectIssues(fields, profile(), "");
    expect(issues).toHaveLength(1);
    expect(issues[0].severity).toBe("error");
    expect(issues[0].fieldId).toBe("1");
  });

  it("warns when a profile value exists but the field is blank", () => {
    const fields: ValField[] = [
      { id: "2", label: "Phone", required: false, value: "", canonicalKey: "phone" },
    ];
    const issues = collectIssues(fields, profile(), "");
    expect(issues).toHaveLength(1);
    expect(issues[0].severity).toBe("warn");
  });

  it("does not warn about blank sensitive EEO fields", () => {
    const fields: ValField[] = [
      { id: "3", label: "Gender", required: false, value: "", canonicalKey: "gender" },
    ];
    expect(collectIssues(fields, profile({ eligibility: { gender: "" } }), "")).toHaveLength(0);
  });

  it("passes a filled required field", () => {
    const fields: ValField[] = [
      { id: "1", label: "First name", required: true, value: "Jane" },
    ];
    expect(collectIssues(fields, profile(), "")).toHaveLength(0);
  });

  it("warns on an experience gap vs the JD", () => {
    const issues = collectIssues([], profile({ yearsOfExperience: 2 }), "7+ years required");
    expect(issues.some((i) => /experience/.test(i.message))).toBe(true);
  });

  it("no experience warning when the candidate meets the bar", () => {
    const issues = collectIssues([], profile({ yearsOfExperience: 8 }), "5+ years required");
    expect(issues.some((i) => /experience/.test(i.message))).toBe(false);
  });
});
