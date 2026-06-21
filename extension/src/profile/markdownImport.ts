import type { CandidateProfile } from "./schema";
import type { Message, MessageResponse } from "@/shared/messages";

/**
 * Turn a markdown resume into a structured profile via the background LLM. If
 * the LLM isn't configured, callers fall back to manual editing — the markdown
 * is still retained (as rawMarkdown) so generation features have context.
 */
export async function extractProfileFromMarkdown(
  markdown: string
): Promise<CandidateProfile> {
  const resp = (await chrome.runtime.sendMessage({
    type: "LLM_EXTRACT_PROFILE",
    markdown,
  } satisfies Message)) as MessageResponse;
  if (resp.ok && "profile" in resp) return resp.profile;
  if (!resp.ok) throw new Error(resp.error);
  throw new Error("Extraction failed.");
}
