/**
 * Networking CRM-lite. One-click captured contacts (from LinkedIn / company
 * pages) with light follow-up tracking. Local in chrome.storage; included in the
 * backup. The search filter is pure and unit-tested.
 */

export interface ContactDraft {
  name?: string;
  role?: string;
  company?: string;
  profileUrl?: string;
  context?: string;
}

export interface Contact extends ContactDraft {
  id: string;
  capturedAt: number;
  /** When the user last reached out — drives follow-up reminders (#56). */
  lastContactedAt?: number;
  notes?: string;
}

const KEY = "appfill:contacts";

export async function getContacts(): Promise<Contact[]> {
  const raw = await chrome.storage.local.get(KEY);
  const list = (raw[KEY] as Contact[]) ?? [];
  return list.sort((a, b) => b.capturedAt - a.capturedAt);
}

async function save(list: Contact[]): Promise<void> {
  await chrome.storage.local.set({ [KEY]: list });
}

export function newContactId(): string {
  return `c_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

export async function addContact(draft: ContactDraft): Promise<Contact> {
  const list = await getContacts();
  // De-dupe on profile URL when present.
  const existing = draft.profileUrl
    ? list.find((c) => c.profileUrl && c.profileUrl === draft.profileUrl)
    : undefined;
  if (existing) {
    Object.assign(existing, draft);
    await save(list);
    return existing;
  }
  const contact: Contact = { ...draft, id: newContactId(), capturedAt: Date.now() };
  await save([contact, ...list]);
  return contact;
}

export async function updateContact(
  id: string,
  patch: Partial<Contact>
): Promise<void> {
  const list = await getContacts();
  const c = list.find((x) => x.id === id);
  if (!c) return;
  Object.assign(c, patch);
  await save(list);
}

export async function removeContact(id: string): Promise<void> {
  await save((await getContacts()).filter((c) => c.id !== id));
}

/** Mark a contact as reached out to now (resets the follow-up clock). */
export async function markContacted(id: string, when = Date.now()): Promise<void> {
  await updateContact(id, { lastContactedAt: when });
}

/**
 * Pure: contacts due for a follow-up — last touch (lastContactedAt, else
 * capture) is at least `cadenceDays` ago. Oldest first.
 */
export function dueContacts(
  list: Contact[],
  cadenceDays: number,
  now = Date.now()
): Contact[] {
  const ms = cadenceDays * 86_400_000;
  const lastTouch = (c: Contact) => c.lastContactedAt ?? c.capturedAt;
  return list
    .filter((c) => now - lastTouch(c) >= ms)
    .sort((a, b) => lastTouch(a) - lastTouch(b));
}

/** Pure: filter contacts by a free-text query over name/company/role. */
export function searchContacts(list: Contact[], query: string): Contact[] {
  const q = query.trim().toLowerCase();
  if (!q) return list;
  return list.filter((c) =>
    [c.name, c.company, c.role, c.context].filter(Boolean).join(" ").toLowerCase().includes(q)
  );
}
