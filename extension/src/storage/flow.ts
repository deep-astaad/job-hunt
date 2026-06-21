/**
 * Multi-page "Fill & Next" flow state. ATS wizards (Workday, Greenhouse, etc.)
 * span several pages — some via SPA route changes, some via full reloads. We
 * persist the flow so it survives a reload and the content script can resume it
 * on the next page.
 */

export interface FlowState {
  active: boolean;
  domain: string;
  step: number;
  startedAt: number;
}

const KEY = "appfill:flow";
const MAX_AGE_MS = 30 * 60_000;

export async function getFlow(): Promise<FlowState | undefined> {
  const raw = await chrome.storage.local.get(KEY);
  const f = raw[KEY] as FlowState | undefined;
  if (!f || !f.active) return undefined;
  if (Date.now() - f.startedAt > MAX_AGE_MS) {
    await clearFlow();
    return undefined;
  }
  return f;
}

export async function setFlow(f: FlowState): Promise<void> {
  await chrome.storage.local.set({ [KEY]: f });
}

export async function clearFlow(): Promise<void> {
  await chrome.storage.local.remove(KEY);
}
