import { describe, it, expect } from "vitest";
import { profileToYaml, yamlToProfile } from "./yaml";
import { emptyProfile, type CandidateProfile } from "./schema";

function sample(): CandidateProfile {
  return {
    contact: {
      firstName: "Jane",
      lastName: "Doe",
      fullName: "Jane Doe",
      email: "jane@example.com",
      phone: "+81 90-1234-5678",
      city: "Tokyo",
      country: "Japan",
    },
    headline: "Backend Engineer",
    summary: "Line one.\nLine two with: a colon.",
    yearsOfExperience: 6,
    currentCompany: "Acme",
    currentTitle: "Senior Engineer",
    skills: ["Python", "Go", "Kubernetes"],
    links: { linkedin: "https://linkedin.com/in/jane", github: "jane" },
    eligibility: {
      workAuthorization: "Authorized to work in Japan",
      requiresSponsorship: false,
      willingToRelocate: true,
      noticePeriod: "1 month",
    },
    workExperience: [
      {
        company: "Acme",
        title: "Senior Engineer",
        location: "Tokyo",
        startDate: "2022-01",
        endDate: "Present",
        current: true,
        bullets: ["Built the thing", "Scaled it 10x"],
      },
      {
        company: "Globex",
        title: "Engineer",
        startDate: "2019",
        endDate: "2021",
        bullets: ["Did work"],
      },
    ],
    education: [
      { school: "MIT", degree: "BSc", field: "CS", startDate: "2015", endDate: "2019" },
    ],
  };
}

describe("master resume yaml round-trip", () => {
  it("preserves a full profile through emit -> parse", () => {
    const p = sample();
    const round = yamlToProfile(profileToYaml(p));
    expect(round.contact).toEqual(p.contact);
    expect(round.headline).toBe(p.headline);
    expect(round.summary).toBe(p.summary);
    expect(round.yearsOfExperience).toBe(6);
    expect(round.skills).toEqual(p.skills);
    expect(round.links).toEqual(p.links);
    expect(round.eligibility.workAuthorization).toBe("Authorized to work in Japan");
    expect(round.eligibility.requiresSponsorship).toBe(false);
    expect(round.eligibility.willingToRelocate).toBe(true);
    expect(round.workExperience).toHaveLength(2);
    expect(round.workExperience[0]).toMatchObject({
      company: "Acme",
      title: "Senior Engineer",
      current: true,
    });
    expect(round.workExperience[0].bullets).toEqual(["Built the thing", "Scaled it 10x"]);
    expect(round.workExperience[1].bullets).toEqual(["Did work"]);
    expect(round.education[0]).toMatchObject({ school: "MIT", degree: "BSc", field: "CS" });
  });

  it("round-trips an empty profile without throwing", () => {
    const round = yamlToProfile(profileToYaml(emptyProfile()));
    expect(round.contact).toEqual({});
    expect(round.skills).toEqual([]);
    expect(round.workExperience).toEqual([]);
  });

  it("parses hand-written YAML with comments and unknown keys", () => {
    const text = `
# a comment
contact:
  firstName: Sam
  email: sam@x.io
headline: Dev
skills:
  - TypeScript
  - React
unknownTopLevel: ignored
`;
    const p = yamlToProfile(text);
    expect(p.contact.firstName).toBe("Sam");
    expect(p.contact.email).toBe("sam@x.io");
    expect(p.headline).toBe("Dev");
    expect(p.skills).toEqual(["TypeScript", "React"]);
  });

  it("handles a quoted value containing a colon", () => {
    const p = yamlToProfile(`headline: "Engineer: backend"\n`);
    expect(p.headline).toBe("Engineer: backend");
  });

  it("preserves blank lines in summary block", () => {
    const p = emptyProfile();
    p.summary = "First paragraph about me.\n\nSecond paragraph about me.";
    const yaml = profileToYaml(p);
    const round = yamlToProfile(yaml);
    expect(round.summary).toBe("First paragraph about me.\n\nSecond paragraph about me.");
  });
});

