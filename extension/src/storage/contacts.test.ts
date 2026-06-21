import { describe, it, expect, beforeEach } from "vitest";
import { addContact, getContacts, removeContact, searchContacts } from "./contacts";

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

describe("contacts store", () => {
  beforeEach(() => installChromeStub());

  it("adds and lists contacts", async () => {
    await addContact({ name: "Ada", company: "Acme", role: "CTO" });
    const list = await getContacts();
    expect(list).toHaveLength(1);
    expect(list[0].id).toBeTruthy();
    expect(list[0].capturedAt).toBeGreaterThan(0);
  });

  it("de-dupes on profile URL (updates in place)", async () => {
    await addContact({ name: "Ada", profileUrl: "https://l.com/ada" });
    await addContact({ name: "Ada L.", company: "Acme", profileUrl: "https://l.com/ada" });
    const list = await getContacts();
    expect(list).toHaveLength(1);
    expect(list[0].name).toBe("Ada L.");
    expect(list[0].company).toBe("Acme");
  });

  it("removes a contact", async () => {
    const c = await addContact({ name: "Bob" });
    await removeContact(c.id);
    expect(await getContacts()).toHaveLength(0);
  });
});

describe("searchContacts", () => {
  const list = [
    { id: "1", capturedAt: 1, name: "Ada Lovelace", company: "Analytical", role: "Engineer" },
    { id: "2", capturedAt: 2, name: "Bob", company: "Globex", role: "Recruiter" },
  ];
  it("filters by name/company/role, case-insensitive", () => {
    expect(searchContacts(list, "globex").map((c) => c.id)).toEqual(["2"]);
    expect(searchContacts(list, "engineer").map((c) => c.id)).toEqual(["1"]);
    expect(searchContacts(list, "")).toHaveLength(2);
  });
});
