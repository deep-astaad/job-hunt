import { detectFields, clearRegistry, getElement, describeElement } from "./detector";
import { detectPlatform } from "./platforms";
import "./platforms/register"; // self-registers platform fill adapters
import { resolveFields } from "./resolver";
import { fillField } from "./filler";
import { highlight, clearHighlights } from "./highlight";
import { installSubmissionCapture } from "./capture";
import { installSuggestions, fillFocused } from "./suggest";
import { fetchResumeFile } from "./resume";
import { extractJobContext } from "./jobContext";
import { installFlow, startFlow, stopFlow } from "./flow";
import { fillWorkHistory } from "./workHistory";
import { runValidation, renderValidationPanel } from "./validate";
import { extractContactInfo } from "./contactInfo";
import { findPageEmails } from "./emails";
import { getSettings, autofillEnabledForDomain } from "@/storage/settings";
import { getProfile, hasProfile } from "@/storage/profile";
import { checkPriorApplication } from "@/storage/applications";
import type { FieldResolution } from "@/shared/types";
import type { Message, MessageResponse } from "@/shared/messages";

const platform = detectPlatform();
const domain = location.hostname;
const isTopFrame = window.top === window;
let lastResolutions: FieldResolution[] = [];

/** Run a full detect -> resolve -> fill -> highlight pass. */
async function runFillPass(force = false): Promise<{
  fieldCount: number;
  filledCount: number;
}> {
  const settings = await getSettings();
  if (!force && !autofillEnabledForDomain(settings, domain)) {
    return { fieldCount: 0, filledCount: 0 };
  }
  if (!(await hasProfile())) return { fieldCount: 0, filledCount: 0 };

  clearRegistry();
  const fields = detectFields();
  if (!fields.length) return { fieldCount: 0, filledCount: 0 };

  const profile = await getProfile();
  const resolutions = await resolveFields(
    fields,
    profile,
    settings,
    domain,
    platform.id
  );

  const resumeFile = await fetchResumeFile();
  let filledCount = 0;
  for (const r of resolutions) {
    const field = fields.find((f) => f.id === r.fieldId);
    if (!field) continue;
    if (r.isResumeFile) {
      if (resumeFile && (await fillField(field, "", platform.id, resumeFile)))
        filledCount++;
      continue;
    }
    if (r.value == null || r.value === "") continue;
    if (await fillField(field, r.value, platform.id)) filledCount++;
  }

  clearHighlights();
  highlight(resolutions, settings.lowConfidenceThreshold);
  lastResolutions = resolutions;

  if (
    settings.autoSubmitDomains.includes(domain) &&
    fields.length > 0 &&
    resolutions.length === fields.length &&
    filledCount > 0
  ) {
    const isSafe = resolutions.every(
      (r) => r.source !== "llm" && r.confidence >= settings.lowConfidenceThreshold
    );
    if (isSafe) {
      startAutoSubmitCountdown();
    }
  }

  return { fieldCount: fields.length, filledCount };
}

/** Fill the LinkedIn "Add a note" connect-modal textarea, if present. */
function fillConnectNote(text: string): boolean {
  const ta = document.querySelector<HTMLTextAreaElement>(
    "#custom-message, textarea[name='message'], .connect-button-send-invite__custom-message"
  );
  if (!ta) return false;
  const proto = Object.getPrototypeOf(ta);
  Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(ta, text);
  ta.dispatchEvent(new Event("input", { bubbles: true }));
  ta.focus();
  return true;
}

function jobTextForValidation(): string {
  try {
    const j = extractJobContext();
    return [j.title, j.company, j.description].filter(Boolean).join("\n");
  } catch {
    return "";
  }
}

/** Fill a returned web-chat answer into the field that requested it. */
async function fillResult(fieldHandle: string, text: string): Promise<void> {
  const el = getElement(fieldHandle);
  if (!el) return;
  const field = describeElement(el);
  if (!field) return;
  await fillField(field, text, platform.id, undefined, true);
}

// --- popup/background message handling ---
chrome.runtime.onMessage.addListener((msg: Message, _sender, sendResponse) => {
  const topFrameOnlyTypes = [
    "FILL_NOW",
    "GET_JOB_CONTEXT",
    "GET_CONTACT_INFO",
    "GET_PAGE_EMAILS",
    "FILL_CONNECT_NOTE",
    "FLOW_START",
    "FLOW_STOP",
    "VALIDATE_FORM",
    "FILL_WORK_HISTORY",
    "GET_STATUS"
  ];
  if (topFrameOnlyTypes.includes(msg.type) && !isTopFrame) {
    return false;
  }

  if (msg.type === "FILL_NOW") {
    runFillPass(true).then(() =>
      sendResponse({ ok: true } satisfies MessageResponse)
    );
    return true;
  }
  if (msg.type === "FILL_FOCUSED") {
    fillFocused().then(() => sendResponse({ ok: true } satisfies MessageResponse));
    return true;
  }
  if (msg.type === "FILL_RESULT") {
    fillResult(msg.fieldHandle, msg.text).then(() =>
      sendResponse({ ok: true } satisfies MessageResponse)
    );
    return true;
  }
  if (msg.type === "GET_JOB_CONTEXT") {
    sendResponse({ ok: true, job: extractJobContext() } satisfies MessageResponse);
    return false;
  }
  if (msg.type === "GET_CONTACT_INFO") {
    sendResponse({ ok: true, contact: extractContactInfo() } satisfies MessageResponse);
    return false;
  }
  if (msg.type === "GET_PAGE_EMAILS") {
    sendResponse({ ok: true, emails: findPageEmails() } satisfies MessageResponse);
    return false;
  }
  if (msg.type === "FILL_CONNECT_NOTE") {
    fillConnectNote(msg.text);
    sendResponse({ ok: true } satisfies MessageResponse);
    return false;
  }
  if (msg.type === "FLOW_START") {
    startFlow().then(() => sendResponse({ ok: true } satisfies MessageResponse));
    return true;
  }
  if (msg.type === "FLOW_STOP") {
    stopFlow().then(() => sendResponse({ ok: true } satisfies MessageResponse));
    return true;
  }
  if (msg.type === "VALIDATE_FORM") {
    getProfile()
      .then((p) => {
        const issues = runValidation(p, platform.id, jobTextForValidation());
        renderValidationPanel(issues);
        return issues.filter((i) => i.severity === "error").length;
      })
      .then((errors) =>
        sendResponse({
          ok: true,
          status: {
            platform: platform.label,
            fieldCount: detectFields().length,
            filledCount: errors, // reused: number of blocking issues
            autofillEnabled: true,
          },
        } satisfies MessageResponse)
      );
    return true;
  }
  if (msg.type === "FILL_WORK_HISTORY") {
    getProfile()
      .then((p) => fillWorkHistory(p))
      .then((count) =>
        sendResponse({
          ok: true,
          status: {
            platform: platform.label,
            fieldCount: detectFields().length,
            filledCount: count,
            autofillEnabled: true,
          },
        } satisfies MessageResponse)
      );
    return true;
  }
  if (msg.type === "GET_STATUS") {
    Promise.all([
      getSettings(),
      (async () => {
        try {
          const job = extractJobContext();
          return await checkPriorApplication(job.url, job.company, job.title);
        } catch {
          return await checkPriorApplication(location.href);
        }
      })()
    ]).then(([s, priorApp]) => {
      const sources = { deterministic: 0, memory: 0, "memory-global": 0, llm: 0 };
      for (const r of lastResolutions) {
        if (r.source) sources[r.source]++;
      }
      sendResponse({
        ok: true,
        status: {
          platform: platform.label,
          fieldCount: detectFields().length,
          filledCount: lastResolutions.length,
          autofillEnabled: autofillEnabledForDomain(s, domain),
          sources,
          priorApplicationDate: priorApp?.appliedAt,
        },
      } satisfies MessageResponse);
    });
    return true;
  }
  return false;
});

// --- lifecycle ---
// Default behavior is passive: on-focus suggestions only. Whole-form auto-fill
// runs on load *only* when the user has opted in (globally or per-site).
installSubmissionCapture(domain, platform.id);
void installSuggestions(domain, platform.id);
installFlow({ fill: () => runFillPass(true), platformId: platform.id, domain });

let debounce: number | undefined;
function schedulePass(): void {
  window.clearTimeout(debounce);
  debounce = window.setTimeout(() => {
    void runFillPass(false);
    reportFillable();
  }, 600);
}

// Tell the background how many fillable fields are on the page so it can badge
// the toolbar icon. Only the top frame reports, to avoid double counting.
function reportFillable(): void {
  if (!isTopFrame) return;
  const count = detectFields().length;
  void chrome.runtime
    .sendMessage({ type: "PAGE_FILLABLE", count } satisfies Message)
    .catch(() => {});
}

// runFillPass already no-ops when autofill is disabled for this domain, so this
// only does work for opted-in sites.
if (document.querySelector("input, textarea, select")) {
  schedulePass();
}
const observer = new MutationObserver(() => {
  if (document.querySelector("input, textarea, select")) schedulePass();
});
observer.observe(document.documentElement, { childList: true, subtree: true });

let submitTimer: number | undefined;

function startAutoSubmitCountdown(): void {
  if (submitTimer) return;

  const submitBtn = Array.from(document.querySelectorAll<HTMLElement>("button, [role='button'], input[type='submit']")).find(btn => {
    const text = (btn.textContent || (btn as HTMLInputElement).value || "").trim().toLowerCase();
    return /(submit|apply|send application|finish|complete application)/.test(text);
  });

  if (!submitBtn) return;

  const banner = document.createElement("div");
  banner.style.cssText = "position:fixed;bottom:20px;right:20px;background:#991b1b;color:white;padding:16px 20px;border-radius:8px;font-family:system-ui,sans-serif;z-index:999999;box-shadow:0 10px 25px rgba(0,0,0,0.2);display:flex;align-items:center;gap:16px;";
  
  const textDiv = document.createElement("div");
  textDiv.style.fontWeight = "bold";
  banner.appendChild(textDiv);
  
  const cancelBtn = document.createElement("button");
  cancelBtn.textContent = "Cancel";
  cancelBtn.style.cssText = "background:rgba(255,255,255,0.2);color:white;border:none;padding:6px 12px;border-radius:4px;cursor:pointer;font-weight:bold;";
  cancelBtn.onclick = () => {
    window.clearInterval(submitTimer);
    submitTimer = undefined;
    banner.remove();
  };
  banner.appendChild(cancelBtn);
  document.body.appendChild(banner);

  let seconds = 5;
  textDiv.textContent = `Auto-submitting in ${seconds}s (all fields highly confident)...`;
  
  submitTimer = window.setInterval(() => {
    seconds--;
    if (seconds <= 0) {
      window.clearInterval(submitTimer);
      submitTimer = undefined;
      banner.remove();
      submitBtn.click();
    } else {
      textDiv.textContent = `Auto-submitting in ${seconds}s (all fields highly confident)...`;
    }
  }, 1000);
}
