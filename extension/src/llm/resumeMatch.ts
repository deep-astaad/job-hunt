/**
 * Deterministic, explainable resume↔job matching. Used to (a) show the user how
 * relevant their profile is to a posting, and (b) auto-pick the best-named
 * resume variant for a job. Pure — no DOM, no network — so it's unit-tested and
 * works with the LLM off.
 */
import type { CandidateProfile } from "@/profile/schema";

const STOPWORDS = new Set(
  ("a an and or the to of in on for with at by from as is are be will you your we our " +
    "this that they their role job work team strong years experience including etc " +
    "ability able help build using used use across into who what when where why how")
    .split(/\s+/)
);

export function tokenize(text: string): string[] {
  return (text.toLowerCase().match(/[a-z0-9][a-z0-9+#.]*/g) ?? []).filter(
    (t) => t.length >= 2 && !STOPWORDS.has(t)
  );
}

/** Does a (possibly multi-word) skill appear in the job text? */
function skillInJob(skill: string, jobLower: string, jdSet: Set<string>): boolean {
  const s = skill.trim().toLowerCase();
  if (!s) return false;
  if (s.includes(" ")) return jobLower.includes(s);
  return jdSet.has(s);
}

export interface ResumeMatch {
  /** 0–100 relevance of the profile to this posting. */
  score: number;
  /** Profile skills that appear in the posting. */
  matchedSkills: string[];
  /** Salient keywords pulled from the posting (for display). */
  jobKeywords: string[];
}

export function matchResumeToJob(
  profile: CandidateProfile,
  jobText: string
): ResumeMatch {
  const jobLower = jobText.toLowerCase();
  const jdTokens = tokenize(jobText);
  const jdSet = new Set(jdTokens);

  const skills = (profile.skills ?? []).map((s) => s.trim()).filter(Boolean);
  const matchedSkills = skills.filter((s) => skillInJob(s, jobLower, jdSet));

  let score: number;
  if (skills.length >= 3) {
    const denom = Math.min(skills.length, 15);
    score = Math.round((100 * Math.min(matchedSkills.length, denom)) / denom);
  } else {
    // Few/no skills listed — fall back to general keyword overlap between the
    // profile text and the posting.
    const profileTokens = new Set(tokenize(profileText(profile)));
    const overlap = jdTokens.filter((t) => profileTokens.has(t)).length;
    score = Math.round(Math.min(100, (100 * overlap) / Math.max(20, jdTokens.length / 4)));
  }

  return { score, matchedSkills, jobKeywords: topKeywords(jdTokens, 12) };
}

function profileText(p: CandidateProfile): string {
  return [
    p.headline,
    p.summary,
    p.skills?.join(" "),
    ...(p.workExperience ?? []).map(
      (w) => `${w.title} ${w.company} ${(w.bullets ?? []).join(" ")}`
    ),
  ]
    .filter(Boolean)
    .join(" ");
}

function topKeywords(tokens: string[], n: number): string[] {
  const counts = new Map<string, number>();
  for (const t of tokens) counts.set(t, (counts.get(t) ?? 0) + 1);
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([t]) => t);
}

export interface ResumeVariantMeta {
  id: string;
  label: string;
  tags: string[];
}

/**
 * Pick the resume variant best matching a posting by scoring each variant's
 * label + tags against the job text. Returns the default (first) when nothing
 * matches. Pure.
 */
export function pickVariantForJob<T extends ResumeVariantMeta>(
  variants: T[],
  jobText: string
): T | undefined {
  if (!variants.length) return undefined;
  const jobLower = jobText.toLowerCase();
  const jdSet = new Set(tokenize(jobText));
  let best = variants[0];
  let bestScore = -1;
  for (const v of variants) {
    const terms = [v.label, ...v.tags]
      .flatMap((t) => t.split(/[\s,/]+/))
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean);
    let score = 0;
    for (const term of terms) {
      if (term.includes(" ") ? jobLower.includes(term) : jdSet.has(term)) score++;
    }
    if (score > bestScore) {
      bestScore = score;
      best = v;
    }
  }
  return best;
}
