/** User-configurable settings, persisted in chrome.storage.local. */

export type LlmMode = "direct" | "webchat" | "off";

export interface Settings {
  // LLM
  /**
   * How generation features get their LLM:
   *  - "direct"  — call the OpenAI-compatible API with the key below (default).
   *  - "webchat" — hand the prompt to a logged-in web chat (no API key needed).
   *  - "off"     — no LLM; deterministic + learned autofill only.
   */
  llmMode: LlmMode;
  /** Provider id for "webchat" mode (see WEB_CHAT_PROVIDERS). */
  webchatProvider: string;
  /** Best-effort auto-paste of the prompt into the chat composer. */
  webchatAutoInject: boolean;
  openaiApiKey: string;
  openaiBaseUrl: string;
  openaiModel: string;
  // Feature toggles
  llmFieldMappingEnabled: boolean;
  coverLetterEnabled: boolean;
  screeningAnswersEnabled: boolean;
  fieldTailoringEnabled: boolean;
  // Fill behavior
  /** Auto-fill the whole form on page load. Off by default — opt in per site. */
  autofillOnLoad: boolean;
  /** Show an inline "fill this field?" suggestion when a field is focused. */
  suggestOnFocus: boolean;
  /** Per-site override of autofill: domain -> enabled. Absent = use global. */
  siteOverrides: Record<string, boolean>;
  /** Domains explicitly allowed to auto-submit the form after a high-confidence fill. */
  autoSubmitDomains: string[];
  /** Confidence below this is badged "review me" and never silently committed. */
  lowConfidenceThreshold: number;
  // Application log (opt-in). When enabled, submissions are POSTed to a backend.
  /** Off by default — keeps AppFill fully self-contained / offline. */
  appLogEnabled: boolean;
  /** Full endpoint URL to POST applications to (e.g. https://host/api/applications/). */
  appLogEndpoint: string;
  appLogToken: string;
  /** Full endpoint URL to POST captured jobs to (e.g. https://host/api/jobs/bulk_create/). */
  jobCaptureEndpoint: string;
  /** Optional bearer token sent as Authorization on the POST to capture jobs. */
  jobCaptureToken: string;
  /** Days after last contact before a networking follow-up is "due". */
  followUpCadenceDays: number;
}

export const DEFAULT_SETTINGS: Settings = {
  llmMode: "direct",
  webchatProvider: "claude",
  webchatAutoInject: true,
  openaiApiKey: "",
  openaiBaseUrl: "https://api.openai.com/v1",
  openaiModel: "gpt-4o-mini",
  llmFieldMappingEnabled: true,
  coverLetterEnabled: true,
  screeningAnswersEnabled: true,
  fieldTailoringEnabled: false,
  autofillOnLoad: false,
  suggestOnFocus: true,
  siteOverrides: {},
  autoSubmitDomains: [],
  lowConfidenceThreshold: 0.6,
  appLogEnabled: false,
  appLogEndpoint: "",
  appLogToken: "",
  jobCaptureEndpoint: "",
  jobCaptureToken: "",
  followUpCadenceDays: 7,
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
