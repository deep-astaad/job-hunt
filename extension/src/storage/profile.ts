import { type CandidateProfile, emptyProfile } from "@/profile/schema";

const KEY = "appfill:profile";

export async function getProfile(): Promise<CandidateProfile> {
  const raw = await chrome.storage.local.get(KEY);
  return { ...emptyProfile(), ...(raw[KEY] ?? {}) };
}

export async function saveProfile(profile: CandidateProfile): Promise<void> {
  await chrome.storage.local.set({ [KEY]: profile });
}

export async function hasProfile(): Promise<boolean> {
  const p = await getProfile();
  return Boolean(p.contact.email || p.contact.fullName || p.contact.firstName);
}
