/**
 * Structured candidate profile that drives autofill.
 *
 * This is the extension's OWN data model. It is intentionally richer than the
 * job-hunt repo's `user-profiles.json` (which only carries ranking signals like
 * skills/experience/salary) because filling an application needs PII, work
 * history, education, and links.
 *
 * The user seeds it from a markdown resume (LLM extraction pass) and/or edits it
 * by hand in the options page.
 */

export interface WorkExperience {
  company: string;
  title: string;
  location?: string;
  startDate?: string; // free text, e.g. "2022-01" or "Jan 2022"
  endDate?: string; // free text or "Present"
  current?: boolean;
  bullets?: string[];
}

export interface Education {
  school: string;
  degree?: string;
  field?: string;
  startDate?: string;
  endDate?: string;
  gpa?: string;
}

export interface ProfileLinks {
  linkedin?: string;
  github?: string;
  portfolio?: string;
  website?: string;
  twitter?: string;
}

/** Common voluntary/EEO + work-eligibility fields applications ask for. */
export interface EligibilityInfo {
  workAuthorization?: string; // e.g. "Authorized to work in Japan"
  requiresSponsorship?: boolean;
  willingToRelocate?: boolean;
  noticePeriod?: string;
  desiredSalary?: string;
  gender?: string;
  raceEthnicity?: string;
  veteranStatus?: string;
  disabilityStatus?: string;
}

export interface ContactInfo {
  firstName?: string;
  lastName?: string;
  fullName?: string;
  email?: string;
  phone?: string;
  addressLine1?: string;
  addressLine2?: string;
  city?: string;
  state?: string;
  postalCode?: string;
  country?: string;
}

export interface CandidateProfile {
  contact: ContactInfo;
  summary?: string;
  headline?: string;
  yearsOfExperience?: number;
  currentCompany?: string;
  currentTitle?: string;
  skills: string[];
  workExperience: WorkExperience[];
  education: Education[];
  links: ProfileLinks;
  eligibility: EligibilityInfo;
  /** Raw markdown the profile was imported from, kept as extra LLM context. */
  rawMarkdown?: string;
}

export function emptyProfile(): CandidateProfile {
  return {
    contact: {},
    skills: [],
    workExperience: [],
    education: [],
    links: {},
    eligibility: {},
  };
}

/**
 * Canonical field keys the deterministic mapper resolves to. A detected form
 * field is matched to one of these, then resolved against the profile by
 * `resolveCanonicalValue`.
 */
export type CanonicalKey =
  | "firstName"
  | "lastName"
  | "fullName"
  | "email"
  | "phone"
  | "addressLine1"
  | "addressLine2"
  | "city"
  | "state"
  | "postalCode"
  | "country"
  | "linkedin"
  | "github"
  | "portfolio"
  | "website"
  | "summary"
  | "headline"
  | "yearsOfExperience"
  | "currentCompany"
  | "currentTitle"
  | "skills"
  | "workAuthorization"
  | "requiresSponsorship"
  | "willingToRelocate"
  | "noticePeriod"
  | "desiredSalary"
  | "gender"
  | "raceEthnicity"
  | "veteranStatus"
  | "disabilityStatus"
  | "resumeFile"
  | "coverLetter";

/** Resolve a canonical key to a string value from the profile (best effort). */
export function resolveCanonicalValue(
  profile: CandidateProfile,
  key: CanonicalKey
): string | undefined {
  const c = profile.contact;
  switch (key) {
    case "firstName":
      return c.firstName ?? c.fullName?.split(" ")[0];
    case "lastName":
      return c.lastName ?? (c.fullName?.split(" ").slice(1).join(" ") || undefined);
    case "fullName":
      return (
        c.fullName ??
        ([c.firstName, c.lastName].filter(Boolean).join(" ") || undefined)
      );
    case "email":
      return c.email;
    case "phone":
      return c.phone;
    case "addressLine1":
      return c.addressLine1;
    case "addressLine2":
      return c.addressLine2;
    case "city":
      return c.city;
    case "state":
      return c.state;
    case "postalCode":
      return c.postalCode;
    case "country":
      return c.country;
    case "linkedin":
      return profile.links.linkedin;
    case "github":
      return profile.links.github;
    case "portfolio":
      return profile.links.portfolio;
    case "website":
      return profile.links.website ?? profile.links.portfolio;
    case "summary":
      return profile.summary;
    case "headline":
      return profile.headline;
    case "yearsOfExperience":
      return profile.yearsOfExperience != null
        ? String(profile.yearsOfExperience)
        : undefined;
    case "currentCompany":
      return profile.currentCompany ?? profile.workExperience[0]?.company;
    case "currentTitle":
      return profile.currentTitle ?? profile.workExperience[0]?.title;
    case "skills":
      return profile.skills.length ? profile.skills.join(", ") : undefined;
    case "workAuthorization":
      return profile.eligibility.workAuthorization;
    case "requiresSponsorship":
      return boolToText(profile.eligibility.requiresSponsorship);
    case "willingToRelocate":
      return boolToText(profile.eligibility.willingToRelocate);
    case "noticePeriod":
      return profile.eligibility.noticePeriod;
    case "desiredSalary":
      return profile.eligibility.desiredSalary;
    case "gender":
      return profile.eligibility.gender;
    case "raceEthnicity":
      return profile.eligibility.raceEthnicity;
    case "veteranStatus":
      return profile.eligibility.veteranStatus;
    case "disabilityStatus":
      return profile.eligibility.disabilityStatus;
    case "resumeFile":
    case "coverLetter":
      return undefined; // handled specially (file attach / generated content)
  }
}

function boolToText(v?: boolean): string | undefined {
  if (v == null) return undefined;
  return v ? "Yes" : "No";
}
