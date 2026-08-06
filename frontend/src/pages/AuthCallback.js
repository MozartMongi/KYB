import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { setAuthToken } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ShieldCheck } from "lucide-react";
import { toast } from "sonner";

export default function AuthCallback() {
  const location = useLocation();
  const navigate = useNavigate();
  const { checkAuth } = useAuth();
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const hash = (location.hash || window.location.hash || "").replace(/^#/, "");
    const params = new URLSearchParams(hash);
    const token = params.get("token");
    const error = params.get("error");

    (async () => {
      if (error) {
        toast.error(decodeURIComponent(error.replace(/\+/g, " ")));
        navigate("/login", { replace: true });
        return;
      }
      if (token) {
        setAuthToken(token);
        window.history.replaceState(null, "", "/auth/callback");
        if (await checkAuth()) {
          navigate("/dashboard", { replace: true });
        } else {
          toast.error("Sesi Google tidak dapat diverifikasi. Silakan masuk kembali.");
          navigate("/login", { replace: true });
        }
        return;
      }
      if (await checkAuth()) {
        navigate("/dashboard", { replace: true });
      } else {
        toast.error("Login Google tidak lengkap. Silakan coba lagi.");
        navigate("/login", { replace: true });
      }
    })();
  }, [location, navigate, checkAuth]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0A0A0A] text-white">
      <div className="flex items-center gap-3 font-head">
        <ShieldCheck className="w-6 h-6 text-blue-500 animate-pulse" />
        <span>Memverifikasi sesi…</span>
      </div>
    </div>
  );
}
