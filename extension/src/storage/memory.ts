/**
 * Learned answer memory. When the user submits an application, every field's
 * signature -> entered value is captured here. On future forms the mapper
 * prefers same-platform answers, then falls back to globally-remembered values
 * (decision: per-domain/ATS with global fallback).
 *
 * Layout: a single record keyed by signature, tracking which platforms/domains
 * the value was seen on plus a global "last value". This keeps lookups O(1) and
 * the store compact.
 */

export interface MemoryEntry {
  signature: string;
  /** Most recent value seen anywhere (global fallback). */
  globalValue: string;
  /** Most recent value per platform id, e.g. { workday: "...", lever: "..." }. */
  byPlatform: Record<string, string>;
  /** Most recent value per domain, e.g. { "boards.greenhouse.io": "..." }. */
  byDomain: Record<string, string>;
  updatedAt: number;
  hitCount: number;
}

const KEY = "appfill:memory";

type MemoryStore = Record<string, MemoryEntry>;

async function load(): Promise<MemoryStore> {
  const raw = await chrome.storage.local.get(KEY);
  return (raw[KEY] as MemoryStore) ?? {};
}

async function persist(store: MemoryStore): Promise<void> {
  await chrome.storage.local.set({ [KEY]: store });
}

export interface MemoryLookup {
  value: string;
  scope: "domain" | "platform" | "global";
}

/**
 * Resolve a remembered value for a signature, preferring same-domain, then
 * same-platform, then the global last value.
 */
export async function recall(
  signature: string,
  domain: string,
  platform: string
): Promise<MemoryLookup | undefined> {
  const store = await load();
  const entry = store[signature];
  if (!entry) return undefined;
  if (entry.byDomain[domain]) return { value: entry.byDomain[domain], scope: "domain" };
  if (entry.byPlatform[platform])
    return { value: entry.byPlatform[platform], scope: "platform" };
  if (entry.globalValue) return { value: entry.globalValue, scope: "global" };
  return undefined;
}

/** Persist a batch of captured (signature -> value) entries from a submission. */
export async function remember(
  entries: { signature: string; value: string }[],
  domain: string,
  platform: string
): Promise<void> {
  const store = await load();
  const now = Date.now();
  for (const { signature, value } of entries) {
    if (!value || !value.trim()) continue;
    const entry: MemoryEntry =
      store[signature] ??
      ({
        signature,
        globalValue: "",
        byPlatform: {},
        byDomain: {},
        updatedAt: now,
        hitCount: 0,
      } as MemoryEntry);
    entry.globalValue = value;
    entry.byPlatform[platform] = value;
    entry.byDomain[domain] = value;
    entry.updatedAt = now;
    entry.hitCount += 1;
    store[signature] = entry;
  }
  await persist(store);
}

export async function getAllMemory(): Promise<MemoryEntry[]> {
  const store = await load();
  return Object.values(store).sort((a, b) => b.updatedAt - a.updatedAt);
}

export async function deleteMemory(signature: string): Promise<void> {
  const store = await load();
  delete store[signature];
  await persist(store);
}

export async function clearMemory(): Promise<void> {
  await chrome.storage.local.remove(KEY);
}
