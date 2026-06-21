import { describe, it, expect } from "vitest";
import { bestOption } from "./filler";

const opts = (labels: string[]) => labels.map((l) => ({ value: l, label: l }));

describe("bestOption (dropdown matching)", () => {
  it("matches exactly, case-insensitively", () => {
    expect(bestOption("United States", opts(["Canada", "United States"]))?.label).toBe(
      "United States"
    );
    expect(bestOption("canada", opts(["Canada", "United States"]))?.label).toBe("Canada");
  });

  it("matches when option text is longer than the value", () => {
    const o = bestOption("Yes", opts(["No", "Yes, I am authorized to work"]));
    expect(o?.label).toBe("Yes, I am authorized to work");
  });

  it("normalizes yes/no to the right option", () => {
    expect(bestOption("true", opts(["No", "Yes"]))?.label).toBe("Yes");
    expect(bestOption("false", opts(["No", "Yes"]))?.label).toBe("No");
  });

  it("matches a value that contains the option label", () => {
    expect(bestOption("Japan (Tokyo)", opts(["Japan", "India"]))?.label).toBe("Japan");
  });

  it("returns undefined when nothing matches", () => {
    expect(bestOption("Brazil", opts(["Japan", "India"]))).toBeUndefined();
  });

  it("ignores empty placeholder options", () => {
    const withPlaceholder = [
      { value: "", label: "Select…" },
      { value: "us", label: "United States" },
    ];
    expect(bestOption("United States", withPlaceholder)?.value).toBe("us");
  });
});
