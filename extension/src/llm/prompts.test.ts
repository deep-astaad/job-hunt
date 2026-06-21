import { describe, it, expect } from "vitest";
import { buildConnectNoteMessages } from "./prompts";
import { emptyProfile } from "@/profile/schema";

describe("buildConnectNoteMessages", () => {
  it("enforces the 300-char limit and embeds the contact + angle", () => {
    const [system, user] = buildConnectNoteMessages(
      { ...emptyProfile(), headline: "Backend Eng" },
      { name: "Ada", company: "Acme", role: "CTO" },
      "referral"
    );
    expect(system.content).toContain("300");
    expect(system.content.toLowerCase()).toContain("referral");
    expect(user.content).toContain("Ada");
    expect(user.content).toContain("Acme");
  });

  it("varies the guidance by angle", () => {
    const alum = buildConnectNoteMessages(emptyProfile(), {}, "alum")[0].content;
    const stack = buildConnectNoteMessages(emptyProfile(), {}, "same_stack")[0].content;
    expect(alum).not.toBe(stack);
    expect(alum.toLowerCase()).toContain("alumni");
  });
});
