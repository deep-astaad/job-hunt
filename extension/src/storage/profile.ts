import {
  type CandidateProfile,
  type CanonicalKey,
  emptyProfile,
  setCanonicalValue,
} from "@/profile/schema";

const KEY = "appfill:profile";

export async function getProfile(): Promise<CandidateProfile> {
  const raw = await chrome.storage.local.get(KEY);
  const data = raw[KEY] ?? {};
  return {
    ...emptyProfile(),
    ...data,
    contact: data.contact ? { ...data.contact } : {},
    skills: data.skills ?? [],
    workExperience: data.workExperience ?? [],
    education: data.education ?? [],
    links: data.links ? { ...data.links } : {},
    eligibility: data.eligibility ? { ...data.eligibility } : {},
  };
}

export async function saveProfile(profile: CandidateProfile): Promise<void> {
  await chrome.storage.local.set({ [KEY]: profile });
}

/** Write a single canonical field into the stored profile and persist it. */
export async function updateProfileField(
  key: CanonicalKey,
  value: string
): Promise<void> {
  const profile = await getProfile();
  await saveProfile(setCanonicalValue(profile, key, value));
}

export async function hasProfile(): Promise<boolean> {
  const p = await getProfile();
  return Boolean(p.contact.email || p.contact.fullName || p.contact.firstName);
}
