import { describe, it, expect } from "vitest";
import { mapFieldDeterministic } from "./mapper";
import { withSignature } from "./signature";
import type { FieldDescriptor } from "@/shared/types";

function field(p: Partial<FieldDescriptor>): FieldDescriptor {
  return withSignature({
    id: "x",
    kind: p.kind ?? "text",
    label: p.label,
    name: p.name,
    domId: p.domId,
    placeholder: p.placeholder,
    autocomplete: p.autocomplete,
    ariaLabel: p.ariaLabel,
  });
}

describe("mapFieldDeterministic", () => {
  it("maps autocomplete tokens with high confidence", () => {
    const m = mapFieldDeterministic(field({ autocomplete: "given-name" }));
    expect(m?.key).toBe("firstName");
    expect(m?.confidence).toBeGreaterThan(0.9);
  });

  it("handles autocomplete section prefixes", () => {
    const m = mapFieldDeterministic(
      field({ autocomplete: "shipping postal-code" })
    );
    expect(m?.key).toBe("postalCode");
  });

  it("distinguishes first name from full name", () => {
    expect(mapFieldDeterministic(field({ label: "First Name" }))?.key).toBe(
      "firstName"
    );
    expect(mapFieldDeterministic(field({ label: "Full Name" }))?.key).toBe(
      "fullName"
    );
  });

  it("maps common contact fields by label", () => {
    expect(mapFieldDeterministic(field({ label: "Email Address" }))?.key).toBe(
      "email"
    );
    expect(mapFieldDeterministic(field({ label: "Mobile Phone" }))?.key).toBe(
      "phone"
    );
    expect(mapFieldDeterministic(field({ label: "LinkedIn URL" }))?.key).toBe(
      "linkedin"
    );
  });

  it("maps a bare file input to the resume", () => {
    const m = mapFieldDeterministic(field({ kind: "file", label: "Resume/CV" }));
    expect(m?.key).toBe("resumeFile");
  });

  it("maps years of experience", () => {
    const m = mapFieldDeterministic(
      field({ label: "How many years of experience do you have?" })
    );
    expect(m?.key).toBe("yearsOfExperience");
  });

  it("maps sponsorship questions", () => {
    const m = mapFieldDeterministic(
      field({ label: "Do you require visa sponsorship?" })
    );
    expect(m?.key).toBe("requiresSponsorship");
  });

  it("maps common EEO and eligibility phrasings", () => {
    const key = (label: string) => mapFieldDeterministic(field({ label }))?.key;
    expect(key("Are you legally authorized to work in the US?")).toBe(
      "workAuthorization"
    );
    expect(key("Do you now or in the future require sponsorship?")).toBe(
      "requiresSponsorship"
    );
    expect(key("Are you open to relocation?")).toBe("willingToRelocate");
    expect(key("What is your notice period?")).toBe("noticePeriod");
    expect(key("Earliest start date")).toBe("availableStartDate");
    expect(key("When can you start?")).toBe("availableStartDate");
    expect(key("Expected salary")).toBe("desiredSalary");
    expect(key("Gender identity")).toBe("gender");
    expect(key("Veteran status")).toBe("veteranStatus");
    expect(key("Disability status")).toBe("disabilityStatus");
    expect(key("Race / Ethnicity")).toBe("raceEthnicity");
  });

  it("keeps start date and notice period distinct", () => {
    const key = (label: string) => mapFieldDeterministic(field({ label }))?.key;
    expect(key("Available start date")).toBe("availableStartDate");
    expect(key("Notice period")).toBe("noticePeriod");
  });

  it("returns undefined for unknown fields", () => {
    expect(
      mapFieldDeterministic(field({ label: "What is your spirit animal?" }))
    ).toBeUndefined();
  });
});
