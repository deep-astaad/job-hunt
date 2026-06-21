import type { Message, MessageResponse } from "@/shared/messages";
import type { FieldDescriptor, FieldResolution } from "@/shared/types";
import { getSettings } from "@/storage/settings";
import { remember } from "@/storage/memory";
import { getResumeFile } from "@/storage/resumeFile";
import { arrayBufferToBase64 } from "@/shared/encoding";
import { chatCompletion, type LlmConfig } from "@/llm/openai";
import {
  buildFieldMappingMessages,
  buildCoverLetterMessages,
  buildScreeningMessages,
  buildTailorMessages,
  buildProfileExtractionMessages,
} from "@/llm/prompts";
import { emptyProfile, type CandidateProfile } from "@/profile/schema";

async function llmConfig(): Promise<LlmConfig> {
  const s = await getSettings();
  return { apiKey: s.openaiApiKey, baseUrl: s.openaiBaseUrl, model: s.openaiModel };
}

chrome.runtime.onMessage.addListener(
  (msg: Message, sender, sendResponse: (r: MessageResponse) => void) => {
    // Toolbar badge: count comes from the page's top frame.
    if (msg.type === "PAGE_FILLABLE") {
      setBadge(sender.tab?.id, msg.count);
      sendResponse({ ok: true });
      return false;
    }
    handle(msg)
      .then(sendResponse)
      .catch((e) =>
        sendResponse({ ok: false, error: e instanceof Error ? e.message : String(e) })
      );
    return true; // async response
  }
);

function setBadge(tabId: number | undefined, count: number): void {
  if (tabId == null) return;
  chrome.action.setBadgeBackgroundColor({ color: "#2563eb" });
  chrome.action.setBadgeText({ tabId, text: count > 0 ? String(count) : "" });
}

// --- context menu: fill this field / this form ---
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "appfill-fill-field",
      title: "AppFill: fill this field",
      contexts: ["editable"],
    });
    chrome.contextMenus.create({
      id: "appfill-fill-form",
      title: "AppFill: fill this form",
      contexts: ["page", "editable"],
    });
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (tab?.id == null) return;
  const type = info.menuItemId === "appfill-fill-field" ? "FILL_FOCUSED" : "FILL_NOW";
  chrome.tabs.sendMessage(tab.id, { type } satisfies Message).catch(() => {});
});

// --- keyboard shortcut ---
chrome.commands?.onCommand.addListener((command) => {
  if (command !== "fill-form") return;
  chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
    if (tab?.id != null)
      chrome.tabs.sendMessage(tab.id, { type: "FILL_NOW" } satisfies Message).catch(() => {});
  });
});

async function handle(msg: Message): Promise<MessageResponse> {
  switch (msg.type) {
    case "LLM_MAP_FIELDS":
      return mapFields(msg.fields, msg.profile);
    case "LLM_GENERATE":
      return generate(msg);
    case "LLM_EXTRACT_PROFILE":
      return extractProfile(msg.markdown);
    case "CAPTURE_SUBMISSION":
      await remember(msg.entries, msg.domain, msg.platform);
      return { ok: true };
    case "GET_RESUME_FILE":
      return resumeFile();
    default:
      return { ok: false, error: "Unhandled message" };
  }
}

async function mapFields(
  fields: FieldDescriptor[],
  profile: CandidateProfile
): Promise<MessageResponse> {
  const cfg = await llmConfig();
  if (!cfg.apiKey) return { ok: true, resolutions: [] };
  const content = await chatCompletion(
    cfg,
    buildFieldMappingMessages(fields, profile),
    { jsonMode: true, temperature: 0.1 }
  );
  const parsed = safeJson(content);
  const mappings: any[] = parsed?.mappings ?? [];
  const resolutions: FieldResolution[] = mappings
    .filter((m) => m && m.fieldId && m.value != null && m.value !== "")
    .map((m) => ({
      fieldId: String(m.fieldId),
      value: String(m.value),
      confidence: clamp01(Number(m.confidence) || 0.5) * 0.85, // discount LLM guesses
      source: "llm" as const,
    }));
  return { ok: true, resolutions };
}

async function generate(
  msg: Extract<Message, { type: "LLM_GENERATE" }>
): Promise<MessageResponse> {
  const cfg = await llmConfig();
  if (!cfg.apiKey) return { ok: false, error: "No OpenAI API key configured." };
  let messages;
  if (msg.kind === "cover_letter") {
    messages = buildCoverLetterMessages(msg.profile, msg.job);
  } else if (msg.kind === "screening_answer") {
    messages = buildScreeningMessages(
      msg.profile,
      msg.prompt ?? "",
      msg.job,
      msg.maxLength
    );
  } else {
    messages = buildTailorMessages(msg.profile, msg.prompt ?? "", msg.maxLength);
  }
  const text = await chatCompletion(cfg, messages, { temperature: 0.5 });
  return { ok: true, text: text.trim() };
}

async function extractProfile(markdown: string): Promise<MessageResponse> {
  const cfg = await llmConfig();
  if (!cfg.apiKey) return { ok: false, error: "No OpenAI API key configured." };
  const content = await chatCompletion(
    cfg,
    buildProfileExtractionMessages(markdown),
    { jsonMode: true, temperature: 0 }
  );
  const parsed = safeJson(content) ?? {};
  const profile: CandidateProfile = {
    ...emptyProfile(),
    ...parsed,
    contact: { ...parsed.contact },
    skills: parsed.skills ?? [],
    workExperience: parsed.workExperience ?? [],
    education: parsed.education ?? [],
    links: parsed.links ?? {},
    eligibility: parsed.eligibility ?? {},
    rawMarkdown: markdown,
  };
  return { ok: true, profile };
}

async function resumeFile(): Promise<MessageResponse> {
  const stored = await getResumeFile();
  if (!stored) return { ok: true, file: undefined };
  return {
    ok: true,
    file: {
      name: stored.name,
      type: stored.type,
      base64: arrayBufferToBase64(stored.data),
    },
  };
}

function safeJson(s: string): any {
  try {
    return JSON.parse(s);
  } catch {
    const m = s.match(/\{[\s\S]*\}/);
    if (m) {
      try {
        return JSON.parse(m[0]);
      } catch {
        /* ignore */
      }
    }
    return null;
  }
}

function clamp01(n: number): number {
  if (Number.isNaN(n)) return 0.5;
  return Math.max(0, Math.min(1, n));
}
