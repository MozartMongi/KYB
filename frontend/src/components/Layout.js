import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { ShieldCheck, LayoutDashboard, FilePlus2, LogOut, Building2 } from "lucide-react";

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const isOfficer = user?.role === "owner" || user?.role === "officer";

  const nav = [
    { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, testid: "nav-dashboard" },
    { to: "/applications/new", label: "Onboarding Baru", icon: FilePlus2, testid: "nav-new-application" },
  ];

  return (
    <div className="min-h-screen flex bg-[#F8F9FA]">
      <aside className="w-64 bg-[#0A0A0A] text-white flex flex-col fixed h-screen">
        <div className="px-5 py-5 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-sm bg-blue-600 flex items-center justify-center">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div className="leading-tight">
              <div className="font-head font-extrabold tracking-tight">CorpScore</div>
              <div className="text-[10px] text-gray-400 tracking-widest">KYB · CRYPTO ID</div>
            </div>
          </div>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {nav.map((n) => {
            const active = location.pathname === n.to;
            const Icon = n.icon;
            return (
              <button
                key={n.to}
                data-testid={n.testid}
                onClick={() => navigate(n.to)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-sm text-sm transition-colors duration-200 ${
                  active ? "bg-blue-600 text-white" : "text-gray-300 hover:bg-white/5"
                }`}
              >
                <Icon className="w-4 h-4" /> {n.label}
              </button>
            );
          })}
        </nav>
        <div className="p-3 border-t border-white/10">
          <div className="px-3 py-2 mb-2">
            <div className="text-sm font-medium truncate">{user?.name}</div>
            <div className="text-[11px] text-gray-400 truncate font-mono">{user?.email}</div>
            <div className="text-[10px] text-blue-400 uppercase tracking-widest mt-1">
              {isOfficer ? "Compliance Officer" : "Applicant"}
            </div>
          </div>
          <button
            data-testid="logout-button"
            onClick={logout}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-sm text-sm text-gray-300 hover:bg-white/5 transition-colors duration-200"
          >
            <LogOut className="w-4 h-4" /> Keluar
          </button>
        </div>
      </aside>
      <main className="flex-1 ml-64 min-h-screen">{children}</main>
    </div>
  );
}
