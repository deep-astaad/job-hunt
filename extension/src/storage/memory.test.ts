import { describe, it, expect, beforeEach } from "vitest";
import { remember, recall, getAllMemory, clearMemory } from "./memory";

// Minimal in-memory chrome.storage.local stub.
function installChromeStub() {
  const store: Record<string, unknown> = {};
  (globalThis as any).chrome = {
    storage: {
      local: {
        get: async (key: string) => ({ [key]: store[key] }),
        set: async (obj: Record<string, unknown>) => Object.assign(store, obj),
        remove: async (key: string) => {
          delete store[key];
        },
      },
    },
  };
}

describe("learned memory precedence", () => {
  beforeEach(async () => {
    installChromeStub();
    await clearMemory();
  });

  it("prefers same-domain, then same-platform, then global", async () => {
    // Seen on greenhouse @ company-a
    await remember([{ signature: "input::phone", value: "111" }], "a.greenhouse.io", "greenhouse");
    // Later seen on lever @ company-b
    await remember([{ signature: "input::phone", value: "222" }], "b.lever.co", "lever");

    // Same exact domain wins.
    expect((await recall("input::phone", "a.greenhouse.io", "greenhouse"))?.value).toBe("111");
    // Different domain, same platform -> platform value.
    expect((await recall("input::phone", "c.greenhouse.io", "greenhouse"))?.value).toBe("111");
    // Unknown domain & platform -> global (most recent) value.
    const g = await recall("input::phone", "x.workday.com", "workday");
    expect(g?.scope).toBe("global");
    expect(g?.value).toBe("222");
  });

  it("ignores empty values", async () => {
    await remember([{ signature: "input::email", value: "  " }], "a.com", "generic");
    expect(await recall("input::email", "a.com", "generic")).toBeUndefined();
  });

  it("returns undefined for unknown signatures", async () => {
    expect(await recall("input::nope", "a.com", "generic")).toBeUndefined();
  });

  it("lists learned entries", async () => {
    await remember([{ signature: "input::city", value: "Tokyo" }], "a.com", "generic");
    const all = await getAllMemory();
    expect(all).toHaveLength(1);
    expect(all[0].globalValue).toBe("Tokyo");
  });
});
