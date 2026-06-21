/**
 * Binary resume storage (PDF/DOCX) in IndexedDB. chrome.storage.local is fine
 * for JSON but awkward for large binaries, so the actual file lives here and is
 * attached to file-upload inputs by the filler.
 */

const DB_NAME = "appfill";
const STORE = "files";
const RESUME_KEY = "resume";

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

export async function saveResumeFile(file: File): Promise<void> {
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
    tx.objectStore(STORE).put(record, RESUME_KEY);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

export async function getResumeFile(): Promise<StoredFile | undefined> {
  const db = await openDb();
  const result = await new Promise<StoredFile | undefined>((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).get(RESUME_KEY);
    req.onsuccess = () => resolve(req.result as StoredFile | undefined);
    req.onerror = () => reject(req.error);
  });
  db.close();
  return result;
}

/** Reconstruct a DOM File from the stored bytes for attaching to <input file>. */
export async function getResumeAsFile(): Promise<File | undefined> {
  const stored = await getResumeFile();
  if (!stored) return undefined;
  return new File([stored.data], stored.name, { type: stored.type });
}

export async function deleteResumeFile(): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(RESUME_KEY);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}
