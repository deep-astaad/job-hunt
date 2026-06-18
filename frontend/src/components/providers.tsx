"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { queryClient } from "@/lib/query";
import { ProfileProvider } from "@/lib/profile-context";
import { FilterProvider } from "@/lib/filter-context";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ProfileProvider>
        <FilterProvider>
          {children}
        </FilterProvider>
      </ProfileProvider>
      <Toaster
        theme="light"
        position="bottom-right"
        toastOptions={{
          classNames: {
            toast: "bg-white border border-border text-ink-primary shadow-md",
            success: "border-l-4 border-l-emerald-500",
            error: "border-l-4 border-l-red-500",
          },
        }}
      />
    </QueryClientProvider>
  );
}

