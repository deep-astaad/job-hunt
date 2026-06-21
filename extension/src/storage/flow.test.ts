import { describe, it, expect, beforeEach } from "vitest";
import { getFlow, setFlow, clearFlow } from "./flow";

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

describe("flow state", () => {
  beforeEach(() => installChromeStub());

  it("round-trips an active flow", async () => {
    await setFlow({ active: true, domain: "x.com", step: 2, startedAt: Date.now() });
    const f = await getFlow();
    expect(f?.active).toBe(true);
    expect(f?.step).toBe(2);
    expect(f?.domain).toBe("x.com");
  });

  it("returns undefined when inactive or cleared", async () => {
    await setFlow({ active: false, domain: "x.com", step: 1, startedAt: Date.now() });
    expect(await getFlow()).toBeUndefined();
    await setFlow({ active: true, domain: "x.com", step: 1, startedAt: Date.now() });
    await clearFlow();
    expect(await getFlow()).toBeUndefined();
  });

  it("expires a stale flow", async () => {
    await setFlow({
      active: true,
      domain: "x.com",
      step: 1,
      startedAt: Date.now() - 60 * 60_000,
    });
    expect(await getFlow()).toBeUndefined();
  });
});
