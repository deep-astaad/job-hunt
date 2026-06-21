import { getProfile, saveProfile } from "./profile";
import { getSettings, saveSettings } from "./settings";
import { dumpMemory, restoreMemory } from "./memory";
import {
  getResumeFile,
  saveResumeFile,
  getResumeFileById,
  saveResumeFileAs,
  DEFAULT_RESUME_ID,
} from "./resumeFile";
import { getResumeVariants, type ResumeVariant } from "./resumeVariants";
import { arrayBufferToBase64, base64ToFile } from "@/shared/encoding";

/**
 * Full backup of everything AppFill stores: profile, settings, learned memory,
 * and resume binaries (default + named variants). Lets the user move between
 * machines or keep a versioned copy. The OpenAI key is included — the file is
 * sensitive, which the UI warns.
 */
export interface BackupVariant {
  meta: ResumeVariant;
  base64: string;
}

export interface Backup {
  app: "appfill";
  version: 1;
  exportedAt: string;
  profile: unknown;
  settings: unknown;
  memory: unknown;
  resume?: { name: string; type: string; base64: string };
  /** Non-default named resume variants. */
  resumeVariants?: BackupVariant[];
}

export async function exportAll(): Promise<Backup> {
  const resume = await getResumeFile();
  const variants = await getResumeVariants();
  const backupVariants: BackupVariant[] = [];
  for (const v of variants) {
    if (v.id === DEFAULT_RESUME_ID) continue; // carried in `resume`
    const f = await getResumeFileById(v.id);
    if (f) backupVariants.push({ meta: v, base64: arrayBufferToBase64(f.data) });
  }
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
    resumeVariants: backupVariants.length ? backupVariants : undefined,
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
  if (data.resumeVariants?.length) {
    for (const v of data.resumeVariants) {
      await saveResumeFileAs(
        v.meta.id,
        base64ToFile(v.base64, v.meta.fileName, v.meta.type)
      );
    }
    await chrome.storage.local.set({
      "appfill:resumeVariants": data.resumeVariants.map((v) => v.meta),
    });
  }
}
