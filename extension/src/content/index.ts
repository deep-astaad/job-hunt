import { detectFields, clearRegistry } from "./detector";
import { detectPlatform } from "./platforms";
import "./platforms/register"; // self-registers platform fill adapters
import { resolveFields } from "./resolver";
import { fillField } from "./filler";
import { highlight, clearHighlights } from "./highlight";
import { installSubmissionCapture } from "./capture";
import { getSettings, autofillEnabledForDomain } from "@/storage/settings";
import { getProfile, hasProfile } from "@/storage/profile";
import type { FieldResolution } from "@/shared/types";
import type { Message, MessageResponse } from "@/shared/messages";
import { base64ToFile } from "@/shared/encoding";

const platform = detectPlatform();
const domain = location.hostname;
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
  return { fieldCount: fields.length, filledCount };
}

async function fetchResumeFile(): Promise<File | undefined> {
  try {
    const resp = (await chrome.runtime.sendMessage({
      type: "GET_RESUME_FILE",
    } satisfies Message)) as MessageResponse;
    if (resp.ok && "file" in resp && resp.file) {
      return base64ToFile(resp.file.base64, resp.file.name, resp.file.type);
    }
  } catch {
    /* no resume stored */
  }
  return undefined;
}

// --- popup/background message handling ---
chrome.runtime.onMessage.addListener((msg: Message, _sender, sendResponse) => {
  if (msg.type === "FILL_NOW") {
    runFillPass(true).then(() =>
      sendResponse({ ok: true } satisfies MessageResponse)
    );
    return true;
  }
  if (msg.type === "GET_STATUS") {
    getSettings().then((s) => {
      sendResponse({
        ok: true,
        status: {
          platform: platform.label,
          fieldCount: detectFields().length,
          filledCount: lastResolutions.length,
          autofillEnabled: autofillEnabledForDomain(s, domain),
        },
      } satisfies MessageResponse);
    });
    return true;
  }
  return false;
});

// --- lifecycle: fill on load, and re-run when SPA forms appear ---
installSubmissionCapture(domain, platform.id);

let debounce: number | undefined;
function schedulePass(): void {
  window.clearTimeout(debounce);
  debounce = window.setTimeout(() => void runFillPass(false), 600);
}

// Only run in the top document or same-origin frames that actually host inputs.
if (document.querySelector("input, textarea, select")) {
  schedulePass();
}
const observer = new MutationObserver(() => {
  if (document.querySelector("input, textarea, select")) schedulePass();
});
observer.observe(document.documentElement, { childList: true, subtree: true });
