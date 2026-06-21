/** User-configurable settings, persisted in chrome.storage.local. */

export interface Settings {
  // LLM
  openaiApiKey: string;
  openaiBaseUrl: string;
  openaiModel: string;
  // Feature toggles
  llmFieldMappingEnabled: boolean;
  coverLetterEnabled: boolean;
  screeningAnswersEnabled: boolean;
  fieldTailoringEnabled: boolean;
  // Fill behavior
  autofillOnLoad: boolean;
  /** Per-site override of autofill: domain -> enabled. Absent = use global. */
  siteOverrides: Record<string, boolean>;
  /** Confidence below this is badged "review me" and never silently committed. */
  lowConfidenceThreshold: number;
}

export const DEFAULT_SETTINGS: Settings = {
  openaiApiKey: "",
  openaiBaseUrl: "https://api.openai.com/v1",
  openaiModel: "gpt-4o-mini",
  llmFieldMappingEnabled: true,
  coverLetterEnabled: true,
  screeningAnswersEnabled: true,
  fieldTailoringEnabled: false,
  autofillOnLoad: true,
  siteOverrides: {},
  lowConfidenceThreshold: 0.6,
};

const KEY = "appfill:settings";

export async function getSettings(): Promise<Settings> {
  const raw = await chrome.storage.local.get(KEY);
  return { ...DEFAULT_SETTINGS, ...(raw[KEY] ?? {}) };
}

export async function saveSettings(patch: Partial<Settings>): Promise<Settings> {
  const current = await getSettings();
  const next = { ...current, ...patch };
  await chrome.storage.local.set({ [KEY]: next });
  return next;
}

/** Is autofill-on-load active for this domain (per-site override wins)? */
export function autofillEnabledForDomain(s: Settings, domain: string): boolean {
  if (domain in s.siteOverrides) return s.siteOverrides[domain];
  return s.autofillOnLoad;
}
