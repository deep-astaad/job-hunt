/**
 * Binary resume storage (PDF/DOCX) in IndexedDB. chrome.storage.local is fine
 * for JSON but awkward for large binaries, so the actual file lives here and is
 * attached to file-upload inputs by the filler.
 *
 * Supports multiple named variants (e.g. "backend", "ml"), each keyed by id in
 * the object store. The default/primary variant uses the id "resume" so the
 * pre-existing single-resume data keeps working unchanged.
 */

const DB_NAME = "appfill";
const STORE = "files";
export const DEFAULT_RESUME_ID = "resume";

export interface StoredFile {
  name: string;
  type: string;
  size: number;
  data: ArrayBuffer;
  updatedAt: number;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function saveResumeFileAs(id: string, file: File): Promise<void> {
  const data = await file.arrayBuffer();
  const record: StoredFile = {
    name: file.name,
    type: file.type || "application/octet-stream",
    size: file.size,
    data,
    updatedAt: Date.now(),
  };
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(record, id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

export async function getResumeFileById(id: string): Promise<StoredFile | undefined> {
  const db = await openDb();
  const result = await new Promise<StoredFile | undefined>((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).get(id);
    req.onsuccess = () => resolve(req.result as StoredFile | undefined);
    req.onerror = () => reject(req.error);
  });
  db.close();
  return result;
}

export async function deleteResumeFileById(id: string): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

// --- backward-compatible single-resume API (operates on the default id) ------

export function saveResumeFile(file: File): Promise<void> {
  return saveResumeFileAs(DEFAULT_RESUME_ID, file);
}

export function getResumeFile(): Promise<StoredFile | undefined> {
  return getResumeFileById(DEFAULT_RESUME_ID);
}

export function deleteResumeFile(): Promise<void> {
  return deleteResumeFileById(DEFAULT_RESUME_ID);
}

/** Reconstruct a DOM File from the stored bytes for attaching to <input file>. */
export async function getResumeAsFile(): Promise<File | undefined> {
  const stored = await getResumeFile();
  if (!stored) return undefined;
  return new File([stored.data], stored.name, { type: stored.type });
}
