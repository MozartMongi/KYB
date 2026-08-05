import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ShieldCheck } from "lucide-react";
import { toast } from "sonner";

/**
 * A session_id is single-use: exchanging it twice fails. Dedupe at module scope so
 * StrictMode's double effect (or a remount mid-exchange) reuses the first promise
 * instead of burning the id and bouncing the user back to /login.
 */
const exchanges = new Map();

function exchangeSession(sessionId) {
  if (!exchanges.has(sessionId)) {
    exchanges.set(
      sessionId,
      api.post("/auth/session", { session_id: sessionId }).then((r) => r.data),
    );
  }
  return exchanges.get(sessionId);
}

export default function AuthCallback() {
  const location = useLocation();
  const navigate = useNavigate();
  const { applySession, checkAuth } = useAuth();
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const hash = location.hash || window.location.hash;
    const sid = new URLSearchParams(hash.replace("#", "")).get("session_id");

    (async () => {
      if (sid) {
        try {
          applySession(await exchangeSession(sid));
          navigate("/dashboard", { replace: true });
          return;
        } catch (e) {
          exchanges.delete(sid);
          console.error("Google session exchange failed", e);
        }
      }
      // The exchange may have failed because it already succeeded (single-use id):
      // trust the cookie/token before sending the user back to the login screen.
      if (await checkAuth()) {
        navigate("/dashboard", { replace: true });
      } else {
        toast.error("Sesi Google tidak dapat diverifikasi. Silakan masuk kembali.");
        navigate("/login", { replace: true });
      }
    })();
  }, [location, navigate, applySession, checkAuth]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0A0A0A] text-white">
      <div className="flex items-center gap-3 font-head">
        <ShieldCheck className="w-6 h-6 text-blue-500 animate-pulse" />
        <span>Memverifikasi sesi…</span>
      </div>
    </div>
  );
}
