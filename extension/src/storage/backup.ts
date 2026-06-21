import { getProfile, saveProfile } from "./profile";
import { getSettings, saveSettings } from "./settings";
import { dumpMemory, restoreMemory } from "./memory";
import { getResumeFile, saveResumeFile } from "./resumeFile";
import { arrayBufferToBase64, base64ToFile } from "@/shared/encoding";

/**
 * Full backup of everything AppFill stores: profile, settings, learned memory,
 * and the resume binary. Lets the user move between machines or keep a versioned
 * copy. The OpenAI key is included — the file is sensitive, which the UI warns.
 */
export interface Backup {
  app: "appfill";
  version: 1;
  exportedAt: string;
  profile: unknown;
  settings: unknown;
  memory: unknown;
  resume?: { name: string; type: string; base64: string };
}

export async function exportAll(): Promise<Backup> {
  const resume = await getResumeFile();
  return {
    app: "appfill",
    version: 1,
    exportedAt: new Date().toISOString(),
    profile: await getProfile(),
    settings: await getSettings(),
    memory: await dumpMemory(),
    resume: resume
      ? {
          name: resume.name,
          type: resume.type,
          base64: arrayBufferToBase64(resume.data),
        }
      : undefined,
  };
}

export async function importAll(data: Backup): Promise<void> {
  if (data?.app !== "appfill") throw new Error("Not an AppFill backup file.");
  if (data.profile) await saveProfile(data.profile as never);
  if (data.settings) await saveSettings(data.settings as never);
  if (data.memory) await restoreMemory(data.memory as never);
  if (data.resume) {
    await saveResumeFile(
      base64ToFile(data.resume.base64, data.resume.name, data.resume.type)
    );
  }
}
