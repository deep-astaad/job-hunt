import type { CanonicalKey } from "@/profile/schema";
import type { FieldDescriptor } from "@/shared/types";
import { normalizeText } from "./signature";
import { platformFieldHint } from "./platforms";

/** HTML autocomplete token -> canonical key (highest-confidence signal). */
const AUTOCOMPLETE_MAP: Record<string, CanonicalKey> = {
  "given-name": "firstName",
  "additional-name": "firstName",
  "family-name": "lastName",
  name: "fullName",
  email: "email",
  username: "email",
  tel: "phone",
  "tel-national": "phone",
  "address-line1": "addressLine1",
  "address-line2": "addressLine2",
  "address-level2": "city",
  "address-level1": "state",
  "postal-code": "postalCode",
  "country-name": "country",
  country: "country",
  organization: "currentCompany",
  "organization-title": "currentTitle",
  url: "website",
};

/**
 * Synonym dictionary: each canonical key has a list of substrings matched
 * against the normalized label/name/placeholder. Order matters — more specific
 * keys are checked before generic ones (see KEY_ORDER).
 */
const SYNONYMS: Record<CanonicalKey, string[]> = {
  firstName: ["first name", "given name", "forename", "legal first"],
  lastName: ["last name", "family name", "surname", "legal last"],
  fullName: ["full name", "your name", "name", "legal name", "applicant name"],
  email: ["email", "e mail"],
  phone: ["phone", "mobile", "telephone", "cell", "contact number"],
  addressLine1: ["address line 1", "street address", "address", "address 1"],
  addressLine2: ["address line 2", "apt", "suite", "unit", "address 2"],
  city: ["city", "town", "municipality", "city town"],
  state: ["state", "province", "region", "prefecture", "county"],
  postalCode: ["postal code", "zip", "zip code", "postcode", "post code"],
  country: ["country", "nation"],
  linkedin: ["linkedin"],
  github: ["github", "git hub"],
  portfolio: ["portfolio"],
  website: ["website", "personal site", "url", "web site", "homepage"],
  summary: ["summary", "about you", "bio", "profile summary"],
  headline: ["headline", "title for yourself", "professional title"],
  yearsOfExperience: [
    "years of experience",
    "years experience",
    "total experience",
    "relevant experience",
    "experience years",
  ],
  currentCompany: ["current company", "current employer", "employer", "company"],
  currentTitle: ["current title", "job title", "current role", "position"],
  skills: ["skills", "technical skills", "key skills"],
  workAuthorization: [
    "work authorization",
    "authorized to work",
    "legally authorized to work",
    "legally authorised to work",
    "are you authorized",
    "right to work",
    "work permit",
    "eligible to work",
    "work eligibility",
    "visa status",
  ],
  requiresSponsorship: [
    "require sponsorship",
    "now or in the future require sponsorship",
    "require immigration sponsorship",
    "require visa sponsorship",
    "need sponsorship",
    "visa sponsorship",
    "sponsorship",
  ],
  willingToRelocate: ["relocate", "willing to relocate", "open to relocation", "relocation"],
  noticePeriod: ["notice period", "current notice", "notice"],
  availableStartDate: [
    "available start date",
    "earliest start date",
    "start date",
    "available to start",
    "when can you start",
    "available from",
    "earliest availability",
  ],
  desiredSalary: [
    "desired salary",
    "expected salary",
    "salary expectation",
    "salary expectations",
    "expected compensation",
    "compensation expectation",
  ],
  gender: ["gender", "gender identity"],
  raceEthnicity: ["race", "ethnicity", "ethnic", "race ethnicity"],
  veteranStatus: ["veteran", "veteran status", "protected veteran"],
  disabilityStatus: ["disability", "disability status"],
  resumeFile: ["resume", "cv", "curriculum vitae", "upload resume", "attach resume"],
  coverLetter: ["cover letter", "motivation letter"],
};

/**
 * Check order: specific multi-word keys before generic single-word ones so
 * "first name" doesn't get swallowed by the generic "name" -> fullName rule.
 */
const KEY_ORDER: CanonicalKey[] = [
  "firstName",
  "lastName",
  "email",
  "phone",
  "linkedin",
  "github",
  "portfolio",
  "addressLine2",
  "addressLine1",
  "postalCode",
  "city",
  "state",
  "country",
  "yearsOfExperience",
  "currentCompany",
  "currentTitle",
  "workAuthorization",
  "requiresSponsorship",
  "willingToRelocate",
  "availableStartDate",
  "noticePeriod",
  "desiredSalary",
  "gender",
  "raceEthnicity",
  "veteranStatus",
  "disabilityStatus",
  "resumeFile",
  "coverLetter",
  "skills",
  "summary",
  "headline",
  "website",
  "fullName",
];

export interface DeterministicMatch {
  key: CanonicalKey;
  confidence: number;
}

/**
 * Map a field to a canonical key deterministically, or return undefined if no
 * confident match (those go to the LLM fallback). Confidence reflects which
 * signal matched: autocomplete token > exact-ish label > substring.
 */
export function mapFieldDeterministic(
  field: FieldDescriptor,
  platformId?: string
): DeterministicMatch | undefined {
  // 0. platform-specific id/name hint — very reliable when present.
  if (platformId) {
    const hinted = platformFieldHint(field, platformId);
    if (hinted) return { key: hinted, confidence: 0.95 };
  }
  // 1. autocomplete attribute — strongest signal.
  if (field.autocomplete) {
    const token = field.autocomplete.split(/\s+/).pop()!; // e.g. "shipping given-name"
    const key = AUTOCOMPLETE_MAP[token] ?? AUTOCOMPLETE_MAP[field.autocomplete];
    if (key) return { key, confidence: 0.97 };
  }
  if (field.kind === "file") {
    const hay = haystack(field);
    // Cover letter check
    if (hay && (containsPhrase(hay, "cover letter") || containsPhrase(hay, "motivation letter") || hay.includes("cover_letter") || hay.includes("coverletter"))) {
      return { key: "coverLetter", confidence: 0.95 };
    }
    // Check if it matches non-resume file types
    if (hay && /portfolio|transcript|sample|certificate|photo|passport|degree|id /i.test(hay)) {
      return undefined;
    }
    // A bare file input on an application is almost always the resume.
    if (!hay || /resume|cv|curriculum|upload|file|attach/.test(hay)) {
      return { key: "resumeFile", confidence: hay ? 0.9 : 0.7 };
    }
  }

  const hay = haystack(field);
  if (!hay) return undefined;

  for (const key of KEY_ORDER) {
    for (const syn of SYNONYMS[key]) {
      if (hay === syn) return { key, confidence: 0.95 }; // whole-label match
      if (containsPhrase(hay, syn)) {
        // Longer, more specific synonyms get higher confidence.
        const conf = syn.includes(" ") ? 0.85 : 0.72;
        return { key, confidence: conf };
      }
    }
  }
  return undefined;
}

function haystack(field: FieldDescriptor): string {
  return normalizeText(
    [field.label, field.ariaLabel, field.placeholder, field.name, field.domId]
      .filter(Boolean)
      .join(" ")
  );
}

/** Word-boundary-ish phrase containment over already-normalized text. */
function containsPhrase(hay: string, phrase: string): boolean {
  return ` ${hay} `.includes(` ${phrase} `) || hay.startsWith(phrase + " ") || hay.endsWith(" " + phrase) || hay === phrase;
}
