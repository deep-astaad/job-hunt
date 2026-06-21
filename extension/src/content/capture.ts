import { detectFields } from "./detector";
import { sendToBackground } from "@/shared/messages";
import { extractJobContext } from "./jobContext";

/**
 * Watch for the user submitting the application and snapshot every field's
 * signature -> entered value, then hand it to the background worker to persist
 * into learned memory. Many ATSs submit via a button click rather than a native
 * form submit, so we listen for both. On submit we also (opt-in) report the
 * application to the configured backend — the background worker no-ops when the
 * log is disabled, so nothing leaves the device by default.
 */
export function installSubmissionCapture(domain: string, platform: string): void {
  const handler = () => {
    captureNow(domain, platform);
    logApplication(platform);
  };

  // Native form submit (capture phase so we run before navigation).
  document.addEventListener("submit", handler, true);

  // Button clicks whose text looks like a submit action.
  document.addEventListener(
    "click",
    (e) => {
      const target = e.target as HTMLElement | null;
      const btn = target?.closest(
        "button, [role='button'], input[type='submit']"
      );
      if (!btn) return;
      const text = (btn.textContent || (btn as HTMLInputElement).value || "")
        .trim()
        .toLowerCase();
      if (/(submit|apply|send application|finish|complete application)/.test(text)) {
        handler();
      }
    },
    true
  );
}

let appLogged = false;

/** Best-effort: report this submission once per page load (background gates it). */
function logApplication(platform: string): void {
  if (appLogged) return;
  appLogged = true;
  let record: { company?: string; role?: string; url?: string; platform: string } = {
    platform,
    url: location.href,
  };
  try {
    const job = extractJobContext();
    record = { company: job.company, role: job.title, url: job.url, platform };
  } catch {
    /* fall back to url only */
  }
  void sendToBackground({ type: "APPLICATION_SUBMITTED", record });
}

function captureNow(domain: string, platform: string): void {
  const fields = detectFields();
  const entries = fields
    .filter((f) => f.existingValue && f.existingValue.trim())
    .map((f) => ({ signature: f.signature, value: f.existingValue!.trim() }));
  if (!entries.length) return;
  void sendToBackground({
    type: "CAPTURE_SUBMISSION",
    domain,
    platform,
    entries,
  });
}
