import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { RiskBadge, StatusBadge } from "@/components/kyb";
import { Button } from "@/components/ui/button";
import { FilePlus2, Building2, AlertTriangle, Clock, TrendingUp } from "lucide-react";

function Stat({ label, value, sub, icon: Icon, accent }) {
  return (
    <div className="bg-white border border-gray-200 rounded-sm p-5" data-testid={`stat-${label}`}>
      <div className="flex items-start justify-between">
        <span className="text-xs text-gray-500 uppercase tracking-wider">{label}</span>
        <Icon className={`w-4 h-4 ${accent}`} />
      </div>
      <div className="font-mono text-3xl font-semibold mt-3">{value}</div>
      {sub && <div className="text-xs text-gray-400 mt-1">{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [apps, setApps] = useState([]);
  const [stats, setStats] = useState(null);
  const isOfficer = user?.role === "owner" || user?.role === "officer";

  useEffect(() => {
    api.get("/applications").then((r) => setApps(r.data)).catch(() => {});
    api.get("/dashboard/stats").then((r) => setStats(r.data)).catch(() => {});
  }, []);

  return (
    <div className="animate-fade-up">
      <header className="bg-white border-b border-gray-200 px-8 py-5 flex items-center justify-between">
        <div>
          <h1 className="font-head font-extrabold text-2xl tracking-tight">
            {isOfficer ? "Antrean Review Compliance" : "Aplikasi KYB Saya"}
          </h1>
          <p className="text-sm text-gray-500">
            {isOfficer ? "Tinjau, nilai, dan putuskan onboarding nasabah perusahaan" : "Pantau status pengajuan onboarding Anda"}
          </p>
        </div>
        <Button data-testid="new-application-button" onClick={() => navigate("/applications/new")} className="rounded-sm bg-black hover:bg-gray-800 gap-2">
          <FilePlus2 className="w-4 h-4" /> Onboarding Baru
        </Button>
      </header>

      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Stat label="Total Aplikasi" value={stats?.total ?? "—"} icon={Building2} accent="text-indigo-600" />
          <Stat label="Menunggu Review" value={stats?.pending_review ?? "—"} icon={Clock} accent="text-blue-600" />
          <Stat label="Risiko Tinggi" value={stats?.risk_counts?.HIGH ?? "—"} icon={AlertTriangle} accent="text-red-600" />
          <Stat label="Rata-rata Skor" value={stats?.avg_score ?? "—"} sub="dari 100" icon={TrendingUp} accent="text-emerald-600" />
        </div>

        <div className="bg-white border border-gray-200 rounded-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
            <h2 className="font-head font-bold">Daftar Onboarding</h2>
            <span className="font-mono text-xs text-gray-400">{apps.length} entri</span>
          </div>
          {apps.length === 0 ? (
            <div className="p-12 text-center text-gray-400">
              <Building2 className="w-10 h-10 mx-auto mb-3 opacity-40" />
              Belum ada aplikasi. Mulai onboarding perusahaan pertama Anda.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 uppercase tracking-wider border-b border-gray-200">
                  <th className="px-5 py-3 font-medium">Perusahaan</th>
                  <th className="px-5 py-3 font-medium">NIB / NPWP</th>
                  <th className="px-5 py-3 font-medium">Industri</th>
                  <th className="px-5 py-3 font-medium">Skor</th>
                  <th className="px-5 py-3 font-medium">Risiko</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {apps.map((a) => (
                  <tr
                    key={a.id}
                    data-testid={`application-row-${a.id}`}
                    onClick={() => navigate(`/applications/${a.id}`)}
                    className="border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors duration-200"
                  >
                    <td className="px-5 py-3.5">
                      <div className="font-medium">{a.company?.legal_name || "Tanpa nama"}</div>
                      <div className="text-xs text-gray-400">{a.company?.entity_type}</div>
                    </td>
                    <td className="px-5 py-3.5 font-mono text-xs text-gray-600">
                      {a.company?.nib || "—"}<br />{a.company?.npwp || "—"}
                    </td>
                    <td className="px-5 py-3.5 text-gray-600">{a.company?.industry}</td>
                    <td className="px-5 py-3.5 font-mono font-semibold">{a.score ? `${a.score.final_score}` : "—"}</td>
                    <td className="px-5 py-3.5">{a.score ? <RiskBadge level={a.score.risk_level} /> : <span className="text-gray-300">—</span>}</td>
                    <td className="px-5 py-3.5"><StatusBadge status={a.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
