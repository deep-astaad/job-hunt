import { describe, it, expect } from "vitest";
import { matchResumeToJob, pickVariantForJob, tokenize } from "./resumeMatch";
import { emptyProfile, type CandidateProfile } from "@/profile/schema";

function profile(skills: string[]): CandidateProfile {
  return { ...emptyProfile(), skills };
}

describe("tokenize", () => {
  it("lowercases, drops stopwords, keeps tech tokens", () => {
    const t = tokenize("We use Go and C++ for the API");
    expect(t).toContain("go");
    expect(t).toContain("c++");
    expect(t).toContain("api");
    expect(t).not.toContain("the");
    expect(t).not.toContain("we");
  });
});

describe("matchResumeToJob", () => {
  const jd = "We need a Go backend engineer with Kubernetes and gRPC. Bonus: Python.";

  it("scores higher when more skills match", () => {
    const few = matchResumeToJob(profile(["Go", "Rust", "Elixir", "Haskell"]), jd);
    const many = matchResumeToJob(
      profile(["Go", "Kubernetes", "gRPC", "Python"]),
      jd
    );
    expect(many.score).toBeGreaterThan(few.score);
  });

  it("reports matched skills found in the posting", () => {
    const m = matchResumeToJob(profile(["Go", "Kubernetes", "PHP"]), jd);
    expect(m.matchedSkills).toContain("Go");
    expect(m.matchedSkills).toContain("Kubernetes");
    expect(m.matchedSkills).not.toContain("PHP");
  });

  it("returns salient job keywords", () => {
    const m = matchResumeToJob(profile(["Go"]), jd);
    expect(m.jobKeywords.length).toBeGreaterThan(0);
    expect(m.jobKeywords).toContain("go");
  });

  it("multi-word skills match as phrases", () => {
    const m = matchResumeToJob(profile(["machine learning"]), "Strong machine learning background");
    expect(m.matchedSkills).toContain("machine learning");
  });
});

describe("pickVariantForJob", () => {
  const variants = [
    { id: "resume", label: "Default", tags: [] },
    { id: "v1", label: "Backend", tags: ["go", "api", "kubernetes"] },
    { id: "v2", label: "Frontend", tags: ["react", "typescript", "css"] },
  ];

  it("picks the variant whose label/tags best match the job", () => {
    const backend = pickVariantForJob(variants, "Go API engineer, Kubernetes");
    expect(backend?.id).toBe("v1");
    const frontend = pickVariantForJob(variants, "React TypeScript UI developer");
    expect(frontend?.id).toBe("v2");
  });

  it("falls back to the first variant when nothing matches", () => {
    const pick = pickVariantForJob(variants, "underwater basket weaving");
    expect(pick?.id).toBe("resume");
  });

  it("returns undefined for an empty list", () => {
    expect(pickVariantForJob([], "anything")).toBeUndefined();
  });
});
