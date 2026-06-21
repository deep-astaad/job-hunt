import { describe, it, expect } from "vitest";
import { DEFAULT_SETTINGS } from "./settings";

describe("default settings safety", () => {
  it("keeps privacy-sensitive features off by default", () => {
    // Application logging must be opt-in (zero network by default).
    expect(DEFAULT_SETTINGS.appLogEnabled).toBe(false);
    expect(DEFAULT_SETTINGS.appLogEndpoint).toBe("");
    // Existing behavior unchanged: API mode default, no whole-form auto-fill.
    expect(DEFAULT_SETTINGS.llmMode).toBe("direct");
    expect(DEFAULT_SETTINGS.autofillOnLoad).toBe(false);
  });
});
