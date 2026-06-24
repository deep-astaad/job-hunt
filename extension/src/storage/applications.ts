export interface AppLogEntry {
  company?: string;
  role?: string;
  url?: string;
  platform: string;
  appliedAt: string;
}

const KEY = "appfill:applications";

export async function getLocalApplications(): Promise<AppLogEntry[]> {
  const raw = await chrome.storage.local.get(KEY);
  return raw[KEY] || [];
}

export async function saveLocalApplication(record: Omit<AppLogEntry, "appliedAt">): Promise<void> {
  const apps = await getLocalApplications();
  apps.push({ ...record, appliedAt: new Date().toISOString() });
  await chrome.storage.local.set({ [KEY]: apps });
}

function normalizeUrl(url: string): string {
  try {
    const u = new URL(url);
    return u.origin + u.pathname;
  } catch {
    return url;
  }
}

export async function checkPriorApplication(url?: string, company?: string, role?: string): Promise<AppLogEntry | undefined> {
  const apps = await getLocalApplications();
  return apps.find(a => {
    if (url && a.url && normalizeUrl(url) === normalizeUrl(a.url)) return true;
    if (company && role && a.company && a.role && company.toLowerCase() === a.company.toLowerCase() && role.toLowerCase() === a.role.toLowerCase()) return true;
    return false;
  });
}
