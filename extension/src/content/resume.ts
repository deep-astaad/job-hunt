import type { Message, MessageResponse } from "@/shared/messages";
import { base64ToFile } from "@/shared/encoding";
import { extractJobContext } from "./jobContext";

/**
 * Fetch the stored resume as a DOM File. The binary lives in the extension's
 * IndexedDB (background origin), which the page-scoped content script can't read
 * directly, so we ask the background worker for the bytes. We pass the page's
 * job text so the background can auto-pick the best-matching resume variant.
 */
export async function fetchResumeFile(): Promise<File | undefined> {
  try {
    const resp = (await chrome.runtime.sendMessage({
      type: "GET_RESUME_FILE",
      jobText: safeJobText(),
    } satisfies Message)) as MessageResponse;
    if (resp.ok && "file" in resp && resp.file) {
      return base64ToFile(resp.file.base64, resp.file.name, resp.file.type);
    }
  } catch {
    /* no resume stored */
  }
  return undefined;
}

function safeJobText(): string | undefined {
  try {
    const j = extractJobContext();
    return [j.title, j.company, j.description].filter(Boolean).join("\n") || undefined;
  } catch {
    return undefined;
  }
}
