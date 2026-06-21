import type { Message, MessageResponse } from "@/shared/messages";
import type { FieldDescriptor, FieldResolution } from "@/shared/types";
import { getSettings } from "@/storage/settings";
import { remember } from "@/storage/memory";
import { getResumeFile, getResumeFileById } from "@/storage/resumeFile";
import { getResumeVariants } from "@/storage/resumeVariants";
import { pickVariantForJob } from "@/llm/resumeMatch";
import { arrayBufferToBase64 } from "@/shared/encoding";
import { chatCompletion, type LlmConfig } from "@/llm/openai";
import {
  buildFieldMappingMessages,
  buildCoverLetterMessages,
  buildScreeningMessages,
  buildTailorMessages,
  buildProfileExtractionMessages,
  buildTailoredResumeMessages,
  buildConnectNoteMessages,
  buildOutreachMessages,
  type OutreachAngle,
} from "@/llm/prompts";
import { emptyProfile, type CandidateProfile } from "@/profile/schema";
import { getProvider, webChatTarget } from "@/llm/webchat/providers";
import {
  setHandoff,
  getHandoff,
  clearHandoff,
  newHandoffId,
} from "@/storage/handoff";

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
    handle(msg, sender)
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

async function handle(
  msg: Message,
  sender?: chrome.runtime.MessageSender
): Promise<MessageResponse> {
  switch (msg.type) {
    case "LLM_MAP_FIELDS":
      return mapFields(msg.fields, msg.profile);
    case "LLM_GENERATE":
      return generate(msg);
    case "LLM_EXTRACT_PROFILE":
      return extractProfile(msg.markdown);
    case "LLM_TAILOR_RESUME":
      return tailorResume(msg);
    case "LLM_CONNECT_NOTE":
      return connectNote(msg);
    case "LLM_OUTREACH":
      return outreach(msg);
    case "CAPTURE_SUBMISSION":
      await remember(msg.entries, msg.domain, msg.platform);
      return { ok: true };
    case "APPLICATION_SUBMITTED":
      await logApplication(msg.record);
      return { ok: true };
    case "GET_RESUME_FILE":
      return resumeFile(msg.jobText);
    case "WEBCHAT_HANDOFF":
      return startWebchatHandoff(msg, sender?.tab?.id);
    case "WEBCHAT_RESULT":
      return relayWebchatResult(msg.id, msg.text);
    default:
      return { ok: false, error: "Unhandled message" };
  }
}

async function startWebchatHandoff(
  msg: Extract<Message, { type: "WEBCHAT_HANDOFF" }>,
  originTabId?: number
): Promise<MessageResponse> {
  const provider = getProvider(msg.providerId);
  if (!provider) return { ok: false, error: `Unknown provider: ${msg.providerId}` };
  const { url } = webChatTarget(provider, msg.prompt);
  const id = newHandoffId();
  await setHandoff({
    id,
    providerId: provider.id,
    prompt: msg.prompt,
    originTabId,
    fieldHandle: msg.fieldHandle,
    consumed: false,
    createdAt: Date.now(),
  });
  await chrome.tabs.create({ url });
  return { ok: true, url };
}

async function relayWebchatResult(
  id: string,
  text: string
): Promise<MessageResponse> {
  const h = await getHandoff();
  if (!h || h.id !== id) return { ok: true }; // stale / already handled
  if (h.originTabId != null && h.fieldHandle) {
    try {
      await chrome.tabs.sendMessage(h.originTabId, {
        type: "FILL_RESULT",
        fieldHandle: h.fieldHandle,
        text,
      } satisfies Message);
      await chrome.tabs.update(h.originTabId, { active: true }).catch(() => {});
    } catch {
      /* origin tab gone — user can still copy/paste manually */
    }
  }
  await clearHandoff();
  return { ok: true };
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

function normalizeProfile(parsed: any, rawMarkdown?: string): CandidateProfile {
  return {
    ...emptyProfile(),
    ...parsed,
    contact: { ...parsed.contact },
    skills: parsed.skills ?? [],
    workExperience: parsed.workExperience ?? [],
    education: parsed.education ?? [],
    links: parsed.links ?? {},
    eligibility: parsed.eligibility ?? {},
    ...(rawMarkdown != null ? { rawMarkdown } : {}),
  };
}

async function extractProfile(markdown: string): Promise<MessageResponse> {
  const cfg = await llmConfig();
  if (!cfg.apiKey) return { ok: false, error: "No OpenAI API key configured." };
  const content = await chatCompletion(
    cfg,
    buildProfileExtractionMessages(markdown),
    { jsonMode: true, temperature: 0 }
  );
  return { ok: true, profile: normalizeProfile(safeJson(content) ?? {}, markdown) };
}

async function tailorResume(
  msg: Extract<Message, { type: "LLM_TAILOR_RESUME" }>
): Promise<MessageResponse> {
  const cfg = await llmConfig();
  if (!cfg.apiKey) return { ok: false, error: "No OpenAI API key configured." };
  const content = await chatCompletion(
    cfg,
    buildTailoredResumeMessages(msg.profile, msg.job),
    { jsonMode: true, temperature: 0.2 }
  );
  const tailored = normalizeProfile(safeJson(content) ?? {}, msg.profile.rawMarkdown);
  // Never let tailoring fabricate identity — keep the real contact + links.
  tailored.contact = { ...msg.profile.contact, ...tailored.contact };
  tailored.links = { ...msg.profile.links, ...tailored.links };
  return { ok: true, profile: tailored };
}

/**
 * Opt-in application log. POSTs the submission to the user-configured backend.
 * Returns silently (no network) when disabled, so AppFill stays self-contained
 * by default.
 */
async function logApplication(record: {
  company?: string;
  role?: string;
  url?: string;
  platform: string;
}): Promise<void> {
  const s = await getSettings();
  if (!s.appLogEnabled || !s.appLogEndpoint) return;
  try {
    await fetch(s.appLogEndpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(s.appLogToken ? { Authorization: `Bearer ${s.appLogToken}` } : {}),
      },
      body: JSON.stringify({
        ...record,
        source: "appfill",
        applied_at: new Date().toISOString(),
      }),
    });
  } catch {
    /* best-effort; never block the user's submission */
  }
}

async function connectNote(
  msg: Extract<Message, { type: "LLM_CONNECT_NOTE" }>
): Promise<MessageResponse> {
  const cfg = await llmConfig();
  if (!cfg.apiKey) return { ok: false, error: "No OpenAI API key configured." };
  const text = await chatCompletion(
    cfg,
    buildConnectNoteMessages(msg.profile, msg.contact, msg.angle as OutreachAngle),
    { temperature: 0.6 }
  );
  return { ok: true, text: text.trim().slice(0, 300) };
}

async function outreach(
  msg: Extract<Message, { type: "LLM_OUTREACH" }>
): Promise<MessageResponse> {
  const cfg = await llmConfig();
  if (!cfg.apiKey) return { ok: false, error: "No OpenAI API key configured." };
  const text = await chatCompletion(
    cfg,
    buildOutreachMessages(msg.profile, msg.contact, msg.draft, msg.job),
    { temperature: 0.5 }
  );
  return { ok: true, text: text.trim() };
}

async function resumeFile(jobText?: string): Promise<MessageResponse> {
  let stored = await pickResume(jobText);
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

/** Choose the resume bytes to attach: best variant for the job, else default. */
async function pickResume(jobText?: string) {
  const variants = await getResumeVariants();
  if (jobText && variants.length > 1) {
    const pick = pickVariantForJob(variants, jobText);
    if (pick) {
      const f = await getResumeFileById(pick.id);
      if (f) return f;
    }
  }
  const def = await getResumeFile();
  if (def) return def;
  return variants[0] ? await getResumeFileById(variants[0].id) : undefined;
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
