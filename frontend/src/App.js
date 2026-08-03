import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Toaster } from "sonner";
import AuthCallback from "@/pages/AuthCallback";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import NewApplication from "@/pages/NewApplication";
import ApplicationDetail from "@/pages/ApplicationDetail";
import Layout from "@/components/Layout";
import { ShieldCheck } from "lucide-react";

function Loader() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0A0A0A] text-white gap-3 font-head">
      <ShieldCheck className="w-6 h-6 text-blue-500 animate-pulse" /> Memuat…
    </div>
  );
}

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <Loader />;
  if (!user) return <Navigate to="/login" replace />;
  return <Layout>{children}</Layout>;
}

function AppRouter() {
  const location = useLocation();
  // Legacy Emergent OAuth returns session_id in the URL hash on any path
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
      <Route path="/applications/new" element={<Protected><NewApplication /></Protected>} />
      <Route path="/applications/:id" element={<Protected><ApplicationDetail /></Protected>} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster position="top-right" richColors />
        <AppRouter />
      </BrowserRouter>
    </AuthProvider>
  );
}
