import type { CandidateProfile } from "@/profile/schema";
import type { FieldDescriptor } from "@/shared/types";
import type { ChatMessage } from "@/llm/openai";
import type { JobContext } from "@/shared/messages";

type Job = JobContext;

function profileDigest(profile: CandidateProfile): string {
  // Prefer the raw markdown (richest), fall back to a compact JSON view.
  if (profile.rawMarkdown && profile.rawMarkdown.trim().length > 40) {
    return profile.rawMarkdown.slice(0, 6000);
  }
  return JSON.stringify(
    {
      contact: profile.contact,
      headline: profile.headline,
      summary: profile.summary,
      yearsOfExperience: profile.yearsOfExperience,
      skills: profile.skills,
      workExperience: profile.workExperience,
      education: profile.education,
      links: profile.links,
      eligibility: profile.eligibility,
    },
    null,
    1
  ).slice(0, 6000);
}

/**
 * Ask the model to map a batch of ambiguous fields to profile-derived values.
 * Returns JSON: { mappings: [{ fieldId, value, confidence }] }.
 */
export function buildFieldMappingMessages(
  fields: FieldDescriptor[],
  profile: CandidateProfile
): ChatMessage[] {
  const compact = fields.map((f) => ({
    fieldId: f.id,
    label: f.label,
    name: f.name,
    placeholder: f.placeholder,
    kind: f.kind,
    section: f.sectionHeading,
    options: f.options?.map((o) => o.label).slice(0, 40),
    maxLength: f.maxLength,
  }));
  const system =
    "You fill job-application forms. Given a candidate profile and a list of form " +
    "fields, return the best value for each field drawn ONLY from the profile. " +
    "If a field cannot be answered from the profile, omit it. For select/radio " +
    "fields, return one of the provided option labels verbatim. Respect maxLength. " +
    "Do not invent facts (no fake dates, employers, or numbers). Respond with " +
    'STRICT JSON: {"mappings":[{"fieldId":"...","value":"...","confidence":0.0-1.0}]}.';
  const user =
    `CANDIDATE PROFILE:\n${profileDigest(profile)}\n\n` +
    `FORM FIELDS:\n${JSON.stringify(compact, null, 1)}`;
  return [
    { role: "system", content: system },
    { role: "user", content: user },
  ];
}

export function buildCoverLetterMessages(
  profile: CandidateProfile,
  job?: Job
): ChatMessage[] {
  const system =
    "Write a concise, specific cover letter (3 short paragraphs, ~180-260 words). " +
    "Ground every claim in the candidate profile; never fabricate experience. " +
    "Professional, warm, no clichés or filler. Return only the letter text.";
  const user =
    `CANDIDATE PROFILE:\n${profileDigest(profile)}\n\n` +
    `JOB:\n${JSON.stringify(job ?? {}, null, 1)}`;
  return [
    { role: "system", content: system },
    { role: "user", content: user },
  ];
}

export function buildScreeningMessages(
  profile: CandidateProfile,
  question: string,
  job?: Job,
  maxLength?: number
): ChatMessage[] {
  const lenHint = maxLength
    ? ` Keep the answer under ${maxLength} characters.`
    : " Keep it to 2-5 sentences.";
  const system =
    "Answer a job-application screening question in first person as the candidate. " +
    "Use only facts from the profile; be specific and honest." +
    lenHint +
    " Return only the answer text.";
  const user =
    `CANDIDATE PROFILE:\n${profileDigest(profile)}\n\n` +
    `JOB:\n${JSON.stringify(job ?? {}, null, 1)}\n\n` +
    `QUESTION:\n${question}`;
  return [
    { role: "system", content: system },
    { role: "user", content: user },
  ];
}

export function buildTailorMessages(
  profile: CandidateProfile,
  fieldLabel: string,
  maxLength?: number
): ChatMessage[] {
  const lenHint = maxLength ? ` Must be under ${maxLength} characters.` : "";
  const system =
    "Produce a value for the named application field, drawn from the candidate " +
    "profile and fitted to any length constraint." +
    lenHint +
    " Return only the value text.";
  const user =
    `CANDIDATE PROFILE:\n${profileDigest(profile)}\n\nFIELD:\n${fieldLabel}`;
  return [
    { role: "system", content: system },
    { role: "user", content: user },
  ];
}

/** Extract a structured profile from a markdown resume. */
export function buildProfileExtractionMessages(markdown: string): ChatMessage[] {
  const system =
    "Extract a structured candidate profile from the markdown resume. Respond " +
    "with STRICT JSON matching this TypeScript shape (omit unknown fields):\n" +
    "{contact:{firstName,lastName,fullName,email,phone,addressLine1,addressLine2," +
    "city,state,postalCode,country}, summary, headline, yearsOfExperience, " +
    "currentCompany, currentTitle, skills:[], workExperience:[{company,title," +
    "location,startDate,endDate,current,bullets:[]}], education:[{school,degree," +
    "field,startDate,endDate,gpa}], links:{linkedin,github,portfolio,website}, " +
    "eligibility:{workAuthorization,requiresSponsorship,willingToRelocate," +
    "noticePeriod,desiredSalary}}. Do not invent data not present in the resume.";
  return [
    { role: "system", content: system },
    { role: "user", content: markdown.slice(0, 12000) },
  ];
}
