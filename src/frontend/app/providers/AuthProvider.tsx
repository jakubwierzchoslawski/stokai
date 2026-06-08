import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { setAccessToken, clearAccessToken } from "../../lib/api/client";
import { fetchMe, postLogin, postLogout, postRefresh, postRegister, type CurrentUser } from "../../features/auth/authApi";

export type AuthState =
  | { status: "loading" }
  | { status: "authenticated"; user: CurrentUser }
  | { status: "anonymous" };

interface AuthContextValue {
  state: AuthState;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: { email: string; username: string; password: string }) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const doLogout = useCallback(async () => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    clearAccessToken();
    try { await postLogout(); } catch { /* ignore */ }
    setState({ status: "anonymous" });
  }, []);

  const scheduleRefresh = useCallback((expSeconds: number) => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    const ms = Math.max((expSeconds - 60) * 1000 - Date.now(), 5_000);
    refreshTimer.current = setTimeout(async () => {
      try {
        const tok = await postRefresh();
        setAccessToken(tok.access_token);
        scheduleRefresh(tok.exp);
      } catch {
        await doLogout();
      }
    }, ms);
  }, [doLogout]);

  const completeLogin = useCallback(
    async (accessToken: string, exp: number) => {
      setAccessToken(accessToken);
      scheduleRefresh(exp);
      const user = await fetchMe();
      setState({ status: "authenticated", user });
    },
    [scheduleRefresh],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const tok = await postRefresh();
        if (cancelled) return;
        await completeLogin(tok.access_token, tok.exp);
      } catch {
        if (!cancelled) setState({ status: "anonymous" });
      }
    })();
    return () => { cancelled = true; };
  }, [completeLogin]);

  useEffect(() => {
    const handler = () => { void doLogout(); };
    window.addEventListener("auth:expired", handler);
    return () => window.removeEventListener("auth:expired", handler);
  }, [doLogout]);

  const value: AuthContextValue = useMemo(
    () => ({
      state,
      login: async (email, password) => {
        const tok = await postLogin(email, password);
        await completeLogin(tok.access_token, tok.exp);
      },
      register: async (payload) => {
        const tok = await postRegister(payload);
        await completeLogin(tok.access_token, tok.exp);
      },
      logout: doLogout,
    }),
    [state, completeLogin, doLogout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}

export function useCurrentUser(): CurrentUser {
  const { state } = useAuth();
  if (state.status !== "authenticated") {
    throw new Error("useCurrentUser called outside an authenticated context");
  }
  return state.user;
}
