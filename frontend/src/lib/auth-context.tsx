"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { fetchMe, logout as apiLogout } from "@/lib/api";
import type { AuthUser } from "@/lib/types";

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  isLoading: true,
  refresh: async () => {},
  signOut: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await fetchMe();
      setUser(me);
    } catch {
      setUser({ authenticated: false });
    }
  }, []);

  const signOut = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      setUser({ authenticated: false });
    }
  }, []);

  useEffect(() => {
    refresh().finally(() => setIsLoading(false));
  }, [refresh]);

  return (
    <AuthContext.Provider value={{ user, isLoading, refresh, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
