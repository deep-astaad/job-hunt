import type { Message, MessageResponse } from "@/shared/messages";
import { base64ToFile } from "@/shared/encoding";

/**
 * Fetch the stored resume as a DOM File. The binary lives in the extension's
 * IndexedDB (background origin), which the page-scoped content script can't read
 * directly, so we ask the background worker for the bytes.
 */
export async function fetchResumeFile(): Promise<File | undefined> {
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
