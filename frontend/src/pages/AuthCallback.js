import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ShieldCheck } from "lucide-react";

export default function AuthCallback() {
  const location = useLocation();
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const processed = useRef(false);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;

    const query = new URLSearchParams(location.search || window.location.search);
    const code = query.get("code");
    const oauthError = query.get("error");

    // Legacy Emergent hash-based session (session_id in URL fragment)
    const hash = location.hash || window.location.hash;
    const sessionId = new URLSearchParams(hash.replace(/^#/, "")).get("session_id");

    if (oauthError) {
      navigate("/login", { replace: true });
      return;
    }

    (async () => {
      try {
        if (code) {
          const redirectUri = `${window.location.origin}/auth/callback`;
          const { data } = await api.post("/auth/google", { code, redirect_uri: redirectUri });
          setUser(data);
          window.history.replaceState(null, "", "/dashboard");
          navigate("/dashboard", { replace: true });
          return;
        }
        if (sessionId) {
          const { data } = await api.post("/auth/session", { session_id: sessionId });
          setUser(data);
          window.history.replaceState(null, "", "/dashboard");
          navigate("/dashboard", { replace: true });
          return;
        }
        navigate("/login", { replace: true });
      } catch {
        navigate("/login", { replace: true });
      }
    })();
  }, [location, navigate, setUser]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0A0A0A] text-white">
      <div className="flex items-center gap-3 font-head">
        <ShieldCheck className="w-6 h-6 text-blue-500 animate-pulse" />
        <span>Memverifikasi sesi…</span>
      </div>
    </div>
  );
}
