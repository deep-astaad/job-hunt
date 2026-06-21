import { describe, it, expect } from "vitest";
import { parseJsonLdJob, stripHtml } from "./jobContext";

describe("parseJsonLdJob", () => {
  it("parses a flat JobPosting", () => {
    const job = parseJsonLdJob(
      JSON.stringify({
        "@context": "https://schema.org",
        "@type": "JobPosting",
        title: "Backend Engineer",
        hiringOrganization: { "@type": "Organization", name: "Acme" },
        description: "<p>Build <b>things</b> with Go.</p>",
      })
    );
    expect(job?.title).toBe("Backend Engineer");
    expect(job?.company).toBe("Acme");
    expect(job?.description).toContain("Build things with Go");
    expect(job?.description).not.toContain("<");
  });

  it("finds a JobPosting inside an @graph", () => {
    const job = parseJsonLdJob(
      JSON.stringify({
        "@graph": [
          { "@type": "WebSite", name: "Board" },
          { "@type": "JobPosting", title: "SRE", hiringOrganization: "Globex" },
        ],
      })
    );
    expect(job?.title).toBe("SRE");
    expect(job?.company).toBe("Globex");
  });

  it("handles an array of nodes and @type arrays", () => {
    const job = parseJsonLdJob(
      JSON.stringify([
        { "@type": ["JobPosting", "Thing"], title: "Data Eng" },
      ])
    );
    expect(job?.title).toBe("Data Eng");
  });

  it("returns undefined for non-job or invalid JSON", () => {
    expect(parseJsonLdJob(JSON.stringify({ "@type": "Article" }))).toBeUndefined();
    expect(parseJsonLdJob("not json")).toBeUndefined();
  });
});

describe("stripHtml", () => {
  it("converts block tags to newlines and decodes entities", () => {
    expect(stripHtml("<p>One</p><p>Two &amp; three</p>")).toBe("One\nTwo & three");
    expect(stripHtml("a<br/>b")).toBe("a\nb");
  });
});
