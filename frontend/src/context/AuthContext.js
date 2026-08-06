import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, clearAuthToken, setAuthToken } from "@/lib/api";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

/** True while the SPA is finishing a Google OAuth return on /auth/callback. */
export function isOAuthCallbackRoute(location) {
  const path = location?.pathname ?? (typeof window !== "undefined" ? window.location.pathname : "");
  return path === "/auth/callback";
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  /** Resolves to the user object, or null when unauthenticated. */
  const checkAuth = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      return data;
    } catch {
      clearAuthToken();
      setUser(false);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  /** Called after login/register/OAuth: persists the bearer fallback and the user. */
  const applySession = useCallback((data) => {
    const { token, ...profile } = data || {};
    if (token) setAuthToken(token);
    setUser(profile);
    setLoading(false);
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined" && window.location.pathname === "/auth/callback") return;
    checkAuth();
  }, [checkAuth]);

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch (e) { console.error("Logout request failed", e); }
    clearAuthToken();
    setUser(false);
    window.location.href = "/login";
  };

  return (
    <AuthContext.Provider value={{ user, setUser, applySession, loading, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
}
