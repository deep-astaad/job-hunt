import { describe, it, expect } from "vitest";
import { profileToResumeHtml } from "./resumeHtml";
import { emptyProfile } from "./schema";

describe("profileToResumeHtml", () => {
  it("renders name, contact, experience and escapes HTML", () => {
    const html = profileToResumeHtml({
      ...emptyProfile(),
      contact: { fullName: "Jane <Doe>", email: "j@x.io", city: "Tokyo" },
      headline: "Engineer",
      skills: ["Go", "Python"],
      workExperience: [
        { company: "Acme", title: "Dev", startDate: "2020", current: true, bullets: ["Did <b>things</b>"] },
      ],
    });
    expect(html).toContain("Jane &lt;Doe&gt;");
    expect(html).toContain("j@x.io");
    expect(html).toContain("Tokyo");
    expect(html).toContain("Dev · Acme");
    expect(html).toContain("Present");
    expect(html).toContain("Did &lt;b&gt;things&lt;/b&gt;");
    expect(html).toContain("Go · Python");
    expect(html.startsWith("<!doctype html>")).toBe(true);
  });

  it("renders a near-empty profile without throwing", () => {
    const html = profileToResumeHtml(emptyProfile());
    expect(html).toContain("Your Name");
  });
});
