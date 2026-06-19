"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import { Sidebar } from "./Sidebar";
import { SettingsModal } from "./SettingsModal";
import { useAuth } from "@/lib/auth-context";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && user && !user.authenticated && pathname !== "/login") {
      router.replace("/login");
    }
  }, [isLoading, user, pathname, router]);

  // Login page renders itself without the shell
  if (pathname === "/login") return <>{children}</>;

  if (isLoading || !user || !user.authenticated) {
    return <div className="min-h-screen bg-base" />;
  }

  return (
    <div className="flex h-screen bg-base overflow-hidden">
      {/* Mobile backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-ink-primary/20 backdrop-blur-sm z-30 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} onOpenSettings={() => setSettingsOpen(true)} />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Mobile top bar */}
        <div className="flex items-center md:hidden px-4 h-12 border-b border-border bg-base-card shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-1.5 -ml-1.5 text-ink-muted hover:text-ink-primary rounded transition-colors"
            aria-label="Open navigation"
          >
            <Menu className="w-5 h-5" />
          </button>
          <span className="ml-3 font-display font-semibold text-base text-ink-primary">JobHunt</span>
        </div>

        <main className="flex-1 overflow-hidden min-h-0">{children}</main>
      </div>

      <SettingsModal isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
