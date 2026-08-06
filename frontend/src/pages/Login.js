import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatAxiosError, API } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ShieldCheck, ArrowRight } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const { applySession } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", name: "" });
  const [loading, setLoading] = useState(false);

  const upd = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const path = mode === "login" ? "/auth/login" : "/auth/register";
      const { data } = await api.post(path, form);
      applySession(data);
      toast.success("Berhasil masuk");
      navigate("/dashboard", { replace: true });
    } catch (err) {
      toast.error(formatAxiosError(err));
    } finally {
      setLoading(false);
    }
  };

  const googleLogin = () => {
    const redirect = `${window.location.origin}/auth/callback`;
    window.location.href = `${API}/auth/google?redirect=${encodeURIComponent(redirect)}`;
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      {/* Left brand panel */}
      <div className="relative hidden lg:flex flex-col justify-between bg-[#0A0A0A] text-white p-12 overflow-hidden grain">
        <img
          src="https://images.unsplash.com/photo-1750969185331-e03829f72c7d?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200"
          alt="" className="absolute inset-0 w-full h-full object-cover opacity-25"
        />
        <div className="relative flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-sm bg-blue-600 flex items-center justify-center">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <span className="font-head font-extrabold text-lg tracking-tight">CorpScore</span>
        </div>
        <div className="relative">
          <h1 className="font-head font-extrabold text-4xl leading-tight tracking-tight">
            KYB & Credit Scoring<br />untuk Crypto Exchange Indonesia
          </h1>
          <p className="mt-4 text-gray-300 max-w-md">
            Onboarding nasabah perusahaan & prioritas dengan standar perbankan — verifikasi dokumen berbasis AI,
            screening PEP/sanksi, dan penilaian risiko kredit yang transparan.
          </p>
          <div className="mt-8 flex gap-6 font-mono text-sm">
            <div><div className="text-2xl font-semibold text-blue-400">4</div><div className="text-gray-400 text-xs">Faktor Skor</div></div>
            <div><div className="text-2xl font-semibold text-blue-400">AI</div><div className="text-gray-400 text-xs">Ekstraksi Dok</div></div>
            <div><div className="text-2xl font-semibold text-blue-400">PPATK</div><div className="text-gray-400 text-xs">Aligned</div></div>
          </div>
        </div>
        <div className="relative text-xs text-gray-500 font-mono">© 2026 CorpScore RegTech</div>
      </div>

      {/* Right form */}
      <div className="flex items-center justify-center p-6 lg:p-12 bg-white">
        <div className="w-full max-w-sm animate-fade-up">
          <h2 className="font-head font-extrabold text-2xl tracking-tight">
            {mode === "login" ? "Masuk ke konsol" : "Buat akun"}
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            {mode === "login" ? "Compliance & onboarding portal" : "Daftar sebagai calon nasabah perusahaan"}
          </p>

          <form onSubmit={submit} className="mt-8 space-y-4">
            {mode === "register" && (
              <div className="space-y-1.5">
                <Label htmlFor="name">Nama lengkap</Label>
                <Input data-testid="name-input" id="name" value={form.name} onChange={upd("name")} required className="rounded-sm" placeholder="Nama Anda" />
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input data-testid="email-input" id="email" type="email" value={form.email} onChange={upd("email")} required className="rounded-sm font-mono" placeholder="anda@perusahaan.id" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Kata sandi</Label>
              <Input data-testid="password-input" id="password" type="password" value={form.password} onChange={upd("password")} required className="rounded-sm" placeholder="••••••••" />
            </div>
            <Button data-testid="submit-auth-button" type="submit" disabled={loading} className="w-full rounded-sm bg-black hover:bg-gray-800 gap-2">
              {loading ? "Memproses…" : mode === "login" ? "Masuk" : "Daftar"} <ArrowRight className="w-4 h-4" />
            </Button>
          </form>

          <div className="my-5 flex items-center gap-3 text-xs text-gray-400">
            <div className="flex-1 h-px bg-gray-200" /> ATAU <div className="flex-1 h-px bg-gray-200" />
          </div>

          <Button data-testid="google-login-button" variant="outline" onClick={googleLogin} className="w-full rounded-sm gap-2 border-gray-300">
            <img src="https://www.svgrepo.com/show/452213/gmail.svg" alt="Gmail" className="w-4 h-4" />
            Lanjut dengan Google
          </Button>

          <p className="mt-6 text-sm text-center text-gray-500">
            {mode === "login" ? "Belum punya akun? " : "Sudah punya akun? "}
            <button
              data-testid="toggle-auth-mode"
              onClick={() => setMode(mode === "login" ? "register" : "login")}
              className="text-blue-600 font-medium hover:underline"
            >
              {mode === "login" ? "Daftar" : "Masuk"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
