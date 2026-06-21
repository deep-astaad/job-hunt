/**
 * Named resume variants. The binary bytes live in IndexedDB (resumeFile.ts);
 * this is the lightweight metadata list (id, label, tags) kept in
 * chrome.storage so the UI and the auto-picker can read it without loading every
 * blob. The default/primary resume appears here as id "resume".
 */
import {
  DEFAULT_RESUME_ID,
  getResumeFileById,
  saveResumeFileAs,
  deleteResumeFileById,
  deleteResumeFile,
} from "./resumeFile";
import type { ResumeVariantMeta } from "@/llm/resumeMatch";

export interface ResumeVariant extends ResumeVariantMeta {
  fileName: string;
  type: string;
  size: number;
  updatedAt: number;
}

const KEY = "appfill:resumeVariants";

async function loadList(): Promise<ResumeVariant[]> {
  const raw = await chrome.storage.local.get(KEY);
  return (raw[KEY] as ResumeVariant[]) ?? [];
}

async function saveList(list: ResumeVariant[]): Promise<void> {
  await chrome.storage.local.set({ [KEY]: list });
}

/**
 * Current variants, reconciled with what's actually in IndexedDB so a default
 * resume uploaded via the legacy single-file path still shows up.
 */
export async function getResumeVariants(): Promise<ResumeVariant[]> {
  let list = await loadList();
  const def = await getResumeFileById(DEFAULT_RESUME_ID);
  const hasDefaultMeta = list.some((v) => v.id === DEFAULT_RESUME_ID);
  if (def && !hasDefaultMeta) {
    list = [
      {
        id: DEFAULT_RESUME_ID,
        label: "Default",
        tags: [],
        fileName: def.name,
        type: def.type,
        size: def.size,
        updatedAt: def.updatedAt,
      },
      ...list,
    ];
  } else if (!def && hasDefaultMeta) {
    list = list.filter((v) => v.id !== DEFAULT_RESUME_ID);
  }
  return list;
}

function newVariantId(): string {
  return `var_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

export async function addResumeVariant(
  file: File,
  label: string,
  tags: string[]
): Promise<void> {
  const id = newVariantId();
  await saveResumeFileAs(id, file);
  const list = await loadList();
  list.push({
    id,
    label: label.trim() || file.name,
    tags: tags.map((t) => t.trim()).filter(Boolean),
    fileName: file.name,
    type: file.type || "application/octet-stream",
    size: file.size,
    updatedAt: Date.now(),
  });
  await saveList(list);
}

export async function removeResumeVariant(id: string): Promise<void> {
  if (id === DEFAULT_RESUME_ID) await deleteResumeFile();
  else await deleteResumeFileById(id);
  await saveList((await loadList()).filter((v) => v.id !== id));
}

export async function updateResumeVariantMeta(
  id: string,
  patch: Partial<Pick<ResumeVariant, "label" | "tags">>
): Promise<void> {
  const list = await loadList();
  // The default may not be persisted yet; materialize it before patching.
  let target = list.find((v) => v.id === id);
  if (!target) {
    const all = await getResumeVariants();
    const found = all.find((v) => v.id === id);
    if (!found) return;
    target = found;
    list.push(found);
  }
  Object.assign(target, patch);
  await saveList(list);
}
