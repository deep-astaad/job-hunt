/**
 * Pending web-chat handoff. When the user starts a BYO-LLM generation, the
 * background worker opens the provider tab and records the prompt + where the
 * answer should return to. The provider content script reads this, injects the
 * prompt, and (best-effort) sends the answer back.
 *
 * A single "current" handoff is kept — handoffs are short-lived and one at a
 * time by nature (the user is driving one chat tab).
 */

export interface Handoff {
  id: string;
  providerId: string;
  prompt: string;
  /** Tab + field the answer should fill, when initiated from a form field. */
  originTabId?: number;
  fieldHandle?: string;
  /** Set true once the provider content script has injected the prompt. */
  consumed: boolean;
  createdAt: number;
}

const KEY = "appfill:handoff";

export async function setHandoff(h: Handoff): Promise<void> {
  await chrome.storage.local.set({ [KEY]: h });
}

export async function getHandoff(): Promise<Handoff | undefined> {
  const raw = await chrome.storage.local.get(KEY);
  const h = raw[KEY] as Handoff | undefined;
  if (!h) return undefined;
  // Expire stale handoffs (15 min) so an old prompt never re-injects.
  if (Date.now() - h.createdAt > 15 * 60_000) return undefined;
  return h;
}

export async function markHandoffConsumed(id: string): Promise<void> {
  const h = await getHandoff();
  if (h && h.id === id) await setHandoff({ ...h, consumed: true });
}

export async function clearHandoff(): Promise<void> {
  await chrome.storage.local.remove(KEY);
}

export function newHandoffId(): string {
  return `h_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}
