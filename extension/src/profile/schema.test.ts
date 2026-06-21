import { describe, it, expect } from "vitest";
import {
  emptyProfile,
  setCanonicalValue,
  resolveCanonicalValue,
  isStorableKey,
} from "./schema";

describe("setCanonicalValue", () => {
  it("writes contact, links, and eligibility into the right slots", () => {
    let p = emptyProfile();
    p = setCanonicalValue(p, "email", "jane@example.com");
    p = setCanonicalValue(p, "github", "https://github.com/jane");
    p = setCanonicalValue(p, "workAuthorization", "Authorized in Japan");
    expect(p.contact.email).toBe("jane@example.com");
    expect(p.links.github).toBe("https://github.com/jane");
    expect(p.eligibility.workAuthorization).toBe("Authorized in Japan");
  });

  it("round-trips with resolveCanonicalValue", () => {
    const p = setCanonicalValue(emptyProfile(), "city", "Tokyo");
    expect(resolveCanonicalValue(p, "city")).toBe("Tokyo");
  });

  it("does not mutate the input profile", () => {
    const p0 = emptyProfile();
    const p1 = setCanonicalValue(p0, "phone", "123");
    expect(p0.contact.phone).toBeUndefined();
    expect(p1.contact.phone).toBe("123");
  });

  it("flags storable vs non-storable keys", () => {
    expect(isStorableKey("email")).toBe(true);
    expect(isStorableKey("resumeFile")).toBe(false);
    expect(isStorableKey("skills")).toBe(false);
  });
});
