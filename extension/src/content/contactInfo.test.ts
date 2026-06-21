import { describe, it, expect } from "vitest";
import { splitHeadline } from "./contactInfo";

describe("splitHeadline", () => {
  it("splits 'Role at Company'", () => {
    expect(splitHeadline("Senior Engineer at Acme")).toEqual({
      role: "Senior Engineer",
      company: "Acme",
    });
  });

  it("handles @ and · separators", () => {
    expect(splitHeadline("CTO @ Globex").company).toBe("Globex");
    expect(splitHeadline("Designer · Initech").company).toBe("Initech");
  });

  it("returns role-only when there's no separator", () => {
    expect(splitHeadline("Open to work")).toEqual({ role: "Open to work" });
  });

  it("returns empty for blank input", () => {
    expect(splitHeadline("  ")).toEqual({});
  });
});
