import type { FieldDescriptor, FieldResolution } from "@/shared/types";
import { type CandidateProfile, resolveCanonicalValue } from "@/profile/schema";
import { mapFieldDeterministic } from "./mapper";
import { recall } from "@/storage/memory";
import { sendToBackground } from "@/shared/messages";
import type { Settings } from "@/storage/settings";

/**
 * Decide a value for every field by fusing three sources, in priority order:
 *   1. Learned memory (per-domain -> per-platform -> global) — what the user
 *      actually submitted before is the strongest signal once it exists.
 *   2. Deterministic mapping — canonical key from label/autocomplete -> profile.
 *   3. LLM fallback — only for whatever is still unresolved (and only if enabled).
 *
 * Mirrors the pipeline's philosophy: deterministic first, LLM as an assist, and
 * everything still works with the LLM turned off.
 */
/**
 * Resolve a single field for the on-focus suggestion, using only memory +
 * deterministic mapping (fast, no network/LLM). Returns undefined if there's
 * nothing confident to suggest.
 */
export async function resolveSingle(
  field: FieldDescriptor,
  profile: CandidateProfile,
  domain: string,
  platform: string
): Promise<FieldResolution | undefined> {
  const det = mapFieldDeterministic(field);

  const mem = await recall(field.signature, domain, platform);
  if (mem) {
    return {
      fieldId: field.id,
      value: mem.value,
      confidence:
        mem.scope === "domain" ? 0.95 : mem.scope === "platform" ? 0.85 : 0.7,
      source: mem.scope === "global" ? "memory-global" : "memory",
      canonicalKey: det?.key,
    };
  }

  if (det) {
    if (det.key === "resumeFile") {
      return {
        fieldId: field.id,
        confidence: det.confidence,
        source: "deterministic",
        canonicalKey: "resumeFile",
        isResumeFile: true,
      };
    }
    const value = resolveCanonicalValue(profile, det.key);
    if (value != null && value !== "") {
      return {
        fieldId: field.id,
        value,
        confidence: det.confidence,
        source: "deterministic",
        canonicalKey: det.key,
      };
    }
  }
  return undefined;
}

export async function resolveFields(
  fields: FieldDescriptor[],
  profile: CandidateProfile,
  settings: Settings,
  domain: string,
  platform: string
): Promise<FieldResolution[]> {
  const resolutions: FieldResolution[] = [];
  const unresolved: FieldDescriptor[] = [];

  for (const field of fields) {
    // Never auto-fill sensitive voluntary EEO selects unless remembered.
    const det = mapFieldDeterministic(field);

    // 1. memory
    const mem = await recall(field.signature, domain, platform);
    if (mem) {
      resolutions.push({
        fieldId: field.id,
        value: mem.value,
        confidence: mem.scope === "domain" ? 0.95 : mem.scope === "platform" ? 0.85 : 0.7,
        source: mem.scope === "global" ? "memory-global" : "memory",
        canonicalKey: det?.key,
      });
      continue;
    }

    // 2. deterministic
    if (det) {
      if (det.key === "resumeFile") {
        resolutions.push({
          fieldId: field.id,
          confidence: det.confidence,
          source: "deterministic",
          canonicalKey: "resumeFile",
          isResumeFile: true,
        });
        continue;
      }
      const value = resolveCanonicalValue(profile, det.key);
      if (value != null && value !== "") {
        resolutions.push({
          fieldId: field.id,
          value,
          confidence: det.confidence,
          source: "deterministic",
          canonicalKey: det.key,
        });
        continue;
      }
    }

    unresolved.push(field);
  }

  // 3. LLM fallback for the remainder
  if (settings.llmFieldMappingEnabled && settings.openaiApiKey && unresolved.length) {
    try {
      const resp = await sendToBackground({
        type: "LLM_MAP_FIELDS",
        fields: unresolved,
        profile,
      });
      if (resp.ok && "resolutions" in resp) {
        resolutions.push(...resp.resolutions);
      }
    } catch {
      // best-effort; deterministic + memory results still stand
    }
  }

  return resolutions;
}
