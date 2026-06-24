"use client";

import { useEffect, useState } from "react";
import { djFetchRaw } from "@/lib/api";

export function ProfilesPage() {
  const [profiles, setProfiles] = useState<any[]>([]);
  const [editing, setEditing] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const res = await djFetchRaw("/profiles/");
      const data = await res.json();
      setProfiles(data.profiles.filter((p: any) => p.id !== "all"));
    } catch(e) {
      console.error(e);
    }
  }

  async function save(p: any) {
    setBusy(true);
    const method = profiles.find((x) => x.id === p.id) ? "PUT" : "POST";
    try {
      await djFetchRaw(`/profiles/${method === "PUT" ? "?id=" + p.id : ""}`, {
        method,
        body: JSON.stringify(p),
      });
      setEditing(null);
      await load();
    } catch(e) {
      alert("Failed to save");
    }
    setBusy(false);
  }

  async function remove(id: string) {
    if (!confirm("Are you sure?")) return;
    setBusy(true);
    try {
      await djFetchRaw(`/profiles/?id=${id}`, { method: "DELETE" });
      await load();
    } catch(e) {
      alert("Failed to delete");
    }
    setBusy(false);
  }

  async function handleGenerate(e: any) {
    const file = e.target.files[0];
    if (!file) return;
    setBusy(true);
    const fd = new FormData();
    fd.append("resume", file);
    try {
      const res = await djFetchRaw("/profiles/generate/", {
        method: "POST",
        body: fd as any,
      });
      const newProfile = await res.json();
      setEditing(newProfile);
    } catch (e) {
      alert("Failed to generate");
    }
    setBusy(false);
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Job Profiles</h1>
      
      {editing ? (
        <div className="bg-white p-6 rounded-lg shadow border">
          <h2 className="text-xl font-bold mb-4">{profiles.find(x => x.id === editing.id) ? "Edit Profile" : "New Profile"}</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">ID (slug)</label>
              <input 
                value={editing.id || ""} 
                disabled={!!profiles.find(x => x.id === editing.id)}
                onChange={e => setEditing({...editing, id: e.target.value})} 
                className="w-full border p-2 rounded" 
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Title</label>
              <input value={editing.title || ""} onChange={e => setEditing({...editing, title: e.target.value})} className="w-full border p-2 rounded" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Experience (string)</label>
              <input value={editing.experience || ""} onChange={e => setEditing({...editing, experience: e.target.value})} className="w-full border p-2 rounded" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Experience Years (number)</label>
              <input type="number" step="0.1" value={editing.experience_years || 0} onChange={e => setEditing({...editing, experience_years: parseFloat(e.target.value)})} className="w-full border p-2 rounded" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Minimum Salary Yen (number)</label>
              <input type="number" value={editing.min_salary_yen || 0} onChange={e => setEditing({...editing, min_salary_yen: parseInt(e.target.value)})} className="w-full border p-2 rounded" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Target Locations (comma separated)</label>
              <input value={(editing.target_locations || []).join(", ")} onChange={e => setEditing({...editing, target_locations: e.target.value.split(",").map((s: string) => s.trim()).filter(Boolean)})} className="w-full border p-2 rounded" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Core Skills (comma separated)</label>
              <input value={(editing.core_skills || []).join(", ")} onChange={e => setEditing({...editing, core_skills: e.target.value.split(",").map((s: string) => s.trim()).filter(Boolean)})} className="w-full border p-2 rounded" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Preferences</label>
              <textarea value={editing.preferences || ""} onChange={e => setEditing({...editing, preferences: e.target.value})} className="w-full border p-2 rounded" rows={3} />
            </div>
          </div>
          <div className="mt-6 flex gap-4">
            <button onClick={() => save(editing)} disabled={busy} className="bg-blue-600 text-white px-4 py-2 rounded">Save</button>
            <button onClick={() => setEditing(null)} disabled={busy} className="px-4 py-2 rounded border">Cancel</button>
          </div>
        </div>
      ) : (
        <>
          <div className="flex gap-4 mb-6">
            <button onClick={() => setEditing({})} className="bg-blue-600 text-white px-4 py-2 rounded">Create New</button>
            <label className="bg-gray-800 text-white px-4 py-2 rounded cursor-pointer">
              {busy ? "Generating..." : "Generate from Resume (.txt)"}
              <input type="file" accept=".txt" onChange={handleGenerate} className="hidden" disabled={busy} />
            </label>
          </div>
          <div className="space-y-4">
            {profiles.map(p => (
              <div key={p.id} className="bg-white p-4 rounded-lg shadow border flex justify-between items-center">
                <div>
                  <h3 className="font-bold text-lg">{p.title}</h3>
                  <p className="text-sm text-gray-600">{p.experience} • {p.target_locations?.join(", ")}</p>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setEditing(p)} className="px-3 py-1 border rounded hover:bg-gray-50">Edit</button>
                  <button onClick={() => remove(p.id)} className="px-3 py-1 border rounded text-red-600 hover:bg-red-50">Delete</button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
