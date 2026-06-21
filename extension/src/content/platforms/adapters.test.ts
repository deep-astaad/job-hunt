import { describe, it, expect } from "vitest";
import "./register"; // registers all adapters as a side effect
import { getAdapter, platformFieldHint } from "./index";
import { mapFieldDeterministic } from "../mapper";
import { withSignature } from "../signature";
import type { FieldDescriptor } from "@/shared/types";

function field(p: Partial<FieldDescriptor>): FieldDescriptor {
  return withSignature({ id: "x", kind: p.kind ?? "text", ...p });
}

describe("platform adapters", () => {
  it("registers the expected adapters with flow selectors", () => {
    for (const id of [
      "workday",
      "greenhouse",
      "lever",
      "ashby",
      "icims",
      "smartrecruiters",
      "linkedin",
    ]) {
      const a = getAdapter(id);
      expect(a, id).toBeDefined();
      const hasFlow =
        (a?.nextSelectors?.length ?? 0) + (a?.submitSelectors?.length ?? 0) > 0;
      expect(hasFlow, id).toBe(true);
    }
  });

  it("maps Greenhouse fields by name via hints", () => {
    expect(
      mapFieldDeterministic(field({ name: "job_application[first_name]" }), "greenhouse")?.key
    ).toBe("firstName");
    expect(
      mapFieldDeterministic(field({ name: "job_application[email]" }), "greenhouse")?.key
    ).toBe("email");
  });

  it("maps Lever's generic name/org/email correctly by precedence", () => {
    expect(mapFieldDeterministic(field({ name: "email" }), "lever")?.key).toBe("email");
    expect(mapFieldDeterministic(field({ name: "org" }), "lever")?.key).toBe("currentCompany");
    expect(mapFieldDeterministic(field({ name: "name" }), "lever")?.key).toBe("fullName");
  });

  it("maps Ashby system fields by id", () => {
    expect(
      platformFieldHint(field({ domId: "_systemfield_email" }), "ashby")
    ).toBe("email");
  });

  it("does not apply hints for an unknown platform", () => {
    expect(platformFieldHint(field({ name: "org" }), "generic")).toBeUndefined();
  });

  it("still falls back to label synonyms when no hint matches", () => {
    expect(
      mapFieldDeterministic(field({ label: "Email Address" }), "greenhouse")?.key
    ).toBe("email");
  });
});
