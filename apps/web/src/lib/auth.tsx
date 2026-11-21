"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, onSessionChange, refreshSession, setAccessToken } from "./api";
import type { TokenResponse, User } from "./types";

type Status = "loading" | "signed-in" | "signed-out";

type AuthContextValue = {
  status: Status;
  user: User | null;
  signIn: (tokens: TokenResponse) => void;
  signOut: () => Promise<void>;
  setUser: (u: User) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    const off = onSessionChange((tokens) => {
      setUser(tokens?.user ?? null);
      setStatus(tokens ? "signed-in" : "signed-out");
    });
    void refreshSession(); // restore the session from the refresh cookie on load
    return () => {
      off();
    };
  }, []);

  // Refresh a minute before the 15-minute access token expires.
  useEffect(() => {
    if (status !== "signed-in") return;
    const id = window.setInterval(() => void refreshSession(), 14 * 60 * 1000);
    return () => window.clearInterval(id);
  }, [status]);

  const signIn = useCallback((tokens: TokenResponse) => {
    setAccessToken(tokens.access_token);
    setUser(tokens.user);
    setStatus("signed-in");
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      setAccessToken(null);
      setUser(null);
      setStatus("signed-out");
    }
  }, []);

  const value = useMemo(
    () => ({ status, user, signIn, signOut, setUser }),
    [status, user, signIn, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
