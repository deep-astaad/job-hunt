"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2, LogIn } from "lucide-react";
import { login } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

export default function LoginPage() {
  const { user, isLoading, refresh } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  // Already authenticated → go home
  useEffect(() => {
    if (!isLoading && user?.authenticated) {
      router.replace("/");
    }
  }, [isLoading, user, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setPending(true);
    try {
      await login(username, password);
      await refresh();
      router.replace("/");
    } catch (err: unknown) {
      setError(err instanceof Error && err.message.includes("401")
        ? "Invalid username or password."
        : "Login failed. Try again.");
    } finally {
      setPending(false);
    }
  };

  if (isLoading) return <div className="min-h-screen bg-base" />;

  return (
    <div className="min-h-screen bg-base flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="text-center mb-8">
          <div className="font-display font-bold text-2xl text-ink-primary tracking-tight leading-none">
            JobHunt
          </div>
          <div className="text-xs text-ink-muted mt-1 uppercase tracking-widest">
            Tokyo Tech Radar
          </div>
        </div>

        {/* Card */}
        <div className="bg-base-surface border border-border rounded-xl shadow-sm p-6 space-y-5">
          <h1 className="text-sm font-semibold text-ink-primary">Sign in to continue</h1>

          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="space-y-1">
              <label className="text-[0.7rem] font-bold text-ink-muted uppercase tracking-widest">
                Username
              </label>
              <input
                type="text"
                autoFocus
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className={inputCls}
                placeholder="admin"
                disabled={pending}
              />
            </div>

            <div className="space-y-1">
              <label className="text-[0.7rem] font-bold text-ink-muted uppercase tracking-widest">
                Password
              </label>
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={inputCls}
                placeholder="••••••••"
                disabled={pending}
              />
            </div>

            {error && (
              <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={pending || !username || !password}
              className={cn(
                "w-full flex items-center justify-center gap-2 py-2 px-4 rounded-md text-sm font-medium transition-colors",
                "bg-brand text-white hover:bg-brand/90 disabled:opacity-50 disabled:cursor-not-allowed"
              )}
            >
              {pending
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <LogIn className="w-4 h-4" />}
              Sign in
            </button>
          </form>

          <p className="text-[0.65rem] text-ink-muted text-center">
            Use your Django admin credentials.{" "}
            <a href="/admin/" className="underline hover:text-ink-primary transition-colors">
              Create account
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}

const inputCls =
  "w-full bg-base-card border border-border rounded-md px-3 py-2 text-sm text-ink-primary placeholder:text-ink-muted focus:border-brand outline-none transition-colors disabled:opacity-60";
