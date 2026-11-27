import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { Api } from "./api/client";
import type { User } from "./api/types";

interface AuthState {
  user: User | null;
  api: Api;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);
const KEY = "testpilot.session";

function load(): { token: string; user: User } | null {
  try {
    return JSON.parse(sessionStorage.getItem(KEY) ?? "null");
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState(load);

  const logout = useCallback(() => {
    sessionStorage.removeItem(KEY);
    setSession(null);
  }, []);

  // token is read on every request, so a new login is picked up without rebuilding the client
  const api = useMemo(() => new Api(() => load()?.token ?? null, logout), [logout]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await api.login(email, password);
      const s = { token: res.token, user: res.user };
      sessionStorage.setItem(KEY, JSON.stringify(s));
      setSession(s);
    },
    [api],
  );

  const value = useMemo(() => ({ user: session?.user ?? null, api, login, logout }), [session, api, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
