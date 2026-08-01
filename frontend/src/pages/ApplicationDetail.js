import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, formatApiErrorDetail, rp } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { RiskBadge, StatusBadge, ScoreGauge, FactorBar } from "@/components/kyb";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { ArrowLeft, ShieldAlert, Sparkles, CheckCircle2, XCircle, Building2, Users, FileText, BadgeCheck, CalendarClock, Ban } from "lucide-react";

export default function ApplicationDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [a, setA] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const isOfficer = user?.role === "owner" || user?.role === "officer";

  const load = () => api.get(`/applications/${id}`).then((r) => setA(r.data)).catch(() => toast.error("Gagal memuat"));
  useEffect(() => { load(); }, [id]);

  const decide = async (decision) => {
    setBusy(true);
    try {
      await api.post(`/applications/${id}/decision`, { decision, note });
      toast.success(decision === "approved" ? "Aplikasi disetujui" : "Aplikasi ditolak");
      load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  if (!a) return <div className="p-8 text-gray-400">Memuat…</div>;
  const co = a.company || {};
  const score = a.score;
  const ai = a.ai_review;
  const val = a.validation;
  const slaDue = a.sla_due_at ? new Date(a.sla_due_at) : null;
  const overdue = slaDue && new Date() > slaDue && a.status === "under_review";

  return (
    <div className="animate-fade-up">
      <header className="bg-white border-b border-gray-200 px-8 py-5">
        <button data-testid="back-button" onClick={() => navigate("/dashboard")} className="text-sm text-gray-500 hover:text-gray-900 flex items-center gap-1.5 mb-2 transition-colors duration-200">
          <ArrowLeft className="w-4 h-4" /> Kembali ke antrean
        </button>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="font-head font-extrabold text-2xl tracking-tight">{co.legal_name}</h1>
            <p className="text-sm text-gray-500 font-mono">{co.entity_type} · {co.industry} · {a.applicant_email}</p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={a.status} />
            {score && <RiskBadge level={score.risk_level} />}
          </div>
        </div>
      </header>

      <div className="p-8 grid lg:grid-cols-3 gap-6">
        {/* Left: score */}
        <div className="space-y-6">
          <div className="bg-white border border-gray-200 rounded-sm p-6 text-center">
            <h2 className="font-head font-bold text-sm uppercase tracking-wider text-gray-500 mb-4">Skor Kredit / Risiko</h2>
            {score ? <ScoreGauge score={score.final_score} /> : <div className="py-8 text-gray-400 text-sm">Belum dinilai</div>}
            {score && (
              <div className="mt-4 text-xs text-gray-500 font-mono">
                Rule-based: {score.overall_rule} · AI adj: {score.ai_adjustment >= 0 ? "+" : ""}{score.ai_adjustment}
              </div>
            )}
          </div>

          {score && (
            <div className="bg-white border border-gray-200 rounded-sm p-6 space-y-4">
              <h2 className="font-head font-bold text-sm uppercase tracking-wider text-gray-500">Faktor Fundamental</h2>
              <FactorBar label="Legalitas (25%)" value={score.legality} />
              <FactorBar label="Keuangan (25%)" value={score.financial} />
              <FactorBar label="Screening AML (30%)" value={score.screening} />
              <FactorBar label="Risiko Industri (20%)" value={score.industry} />
            </div>
          )}
        </div>

        {/* Middle+Right: details */}
        <div className="lg:col-span-2 space-y-6">
          {a.status === "auto_rejected" && (
            <div data-testid="auto-reject-banner" className="bg-red-100 border border-red-400 rounded-sm p-4 flex items-start gap-3">
              <Ban className="w-5 h-5 text-red-700 shrink-0 mt-0.5" />
              <div>
                <div className="font-head font-bold text-red-800">AUTO-REJECTED oleh sistem</div>
                <div className="text-sm text-red-700">{a.auto_reject_reason || "Validasi otomatis gagal"}</div>
              </div>
            </div>
          )}

          {/* System validation */}
          {val && (
            <div className="bg-white border border-gray-200 rounded-sm p-6" data-testid="validation-card">
              <h2 className="font-head font-bold flex items-center gap-2 mb-4"><BadgeCheck className="w-4 h-4 text-blue-600" /> Validasi Sistem</h2>
              <div className="grid sm:grid-cols-2 gap-4">
                <div className="border border-gray-200 rounded-sm p-4" data-testid="nib-validation">
                  <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">Verifikasi NIB</div>
                  <div className="flex items-center gap-2">
                    {val.nib?.valid ? <CheckCircle2 className="w-4 h-4 text-emerald-600" /> : <Ban className="w-4 h-4 text-red-600" />}
                    <span className={`font-mono text-sm font-semibold ${val.nib?.valid ? "text-emerald-700" : "text-red-700"}`}>
                      {val.nib?.valid ? "VALID" : val.nib?.expired ? "KEDALUWARSA" : "TIDAK VALID"}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">Masa berlaku: <span className="font-mono">{val.nib?.nib_expiry_date || "—"}</span></div>
                  {val.nib?.qr && val.nib.qr.success && (
                    <div className="text-xs text-gray-500 mt-1">QR: <span className="font-mono">{val.nib.qr.domain_valid ? "oss.go.id ✓" : "domain tidak valid"}</span> · NIB {val.nib.qr.matches_input ? "cocok" : "tidak cocok"}</div>
                  )}
                  {val.nib?.registry && (
                    <div className="text-xs text-gray-500">Registry: <span className="font-mono">{val.nib.registry.source} · {val.nib.registry.status || "-"}</span></div>
                  )}
                  {val.nib?.reason && <div className="text-xs text-red-600 mt-1">{val.nib.reason}</div>}
                </div>
                <div className="border border-gray-200 rounded-sm p-4" data-testid="bank-validation">
                  <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">Verifikasi Rekening Bank</div>
                  <div className="flex items-center gap-2">
                    {val.bank?.verified ? <CheckCircle2 className="w-4 h-4 text-emerald-600" /> : <ShieldAlert className="w-4 h-4 text-amber-600" />}
                    <span className={`font-mono text-sm font-semibold ${val.bank?.verified ? "text-emerald-700" : "text-amber-700"}`}>{(val.bank?.status || "unverified").toUpperCase()}</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">{val.bank?.bank_name || "—"} · <span className="font-mono">{val.bank?.account_number_masked || "—"}</span></div>
                  <div className="text-xs text-gray-500">Sumber: <span className="font-mono">{val.bank?.source || "—"}</span>{val.bank?.resolved_name ? <> · Nama bank: <span className="font-mono">{val.bank.resolved_name}</span></> : null}</div>
                  <div className="text-xs text-gray-500">Kecocokan nama: <span className="font-mono">{val.bank?.name_match_score ?? 0}%</span></div>
                  {val.bank?.note && <div className="text-xs text-gray-500 mt-1">{val.bank.note}</div>}
                </div>
                {a.sla_due_at && a.status === "under_review" && (
                  <div data-testid="sla-banner" className={`sm:col-span-2 flex items-center gap-2 rounded-sm p-3 border ${overdue ? "bg-red-50 border-red-200 text-red-700" : "bg-blue-50 border-blue-200 text-blue-700"}`}>
                    <CalendarClock className="w-4 h-4" />
                    <span className="text-sm">Target SLA peninjauan manual: <b className="font-mono">{slaDue.toLocaleDateString("id-ID")}</b> (3 hari kerja){overdue ? " — TERLAMBAT" : ""}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* AI review */}
          {ai && (
            <div className="bg-white border border-gray-200 rounded-sm p-6">
              <h2 className="font-head font-bold flex items-center gap-2 mb-3"><Sparkles className="w-4 h-4 text-indigo-600" /> Analisa AI Compliance</h2>
              <p className="text-sm text-gray-700 leading-relaxed">{ai.narrative}</p>
              {ai.red_flags?.length > 0 && (
                <div className="mt-4">
                  <div className="text-xs font-semibold text-red-600 uppercase tracking-wider mb-2">Red Flags</div>
                  <ul className="space-y-1">{ai.red_flags.map((f, i) => <li key={i} className="text-sm text-gray-700 flex gap-2"><ShieldAlert className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />{f}</li>)}</ul>
                </div>
              )}
              {ai.recommended_edd?.length > 0 && (
                <div className="mt-4">
                  <div className="text-xs font-semibold text-blue-600 uppercase tracking-wider mb-2">Rekomendasi Enhanced Due Diligence</div>
                  <ul className="space-y-1 list-disc pl-5">{ai.recommended_edd.map((f, i) => <li key={i} className="text-sm text-gray-700">{f}</li>)}</ul>
                </div>
              )}
            </div>
          )}

          {/* Screening */}
          <div className="bg-white border border-gray-200 rounded-sm p-6">
            <h2 className="font-head font-bold flex items-center gap-2 mb-3"><ShieldAlert className="w-4 h-4 text-amber-600" /> Screening Sanksi / PEP / Adverse Media</h2>
            {a.screening_hits?.length ? (
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-gray-500 uppercase border-b border-gray-200"><th className="py-2">Nama Cocok</th><th className="py-2">Tipe</th><th className="py-2">Daftar</th></tr></thead>
                <tbody>{a.screening_hits.map((h, i) => (
                  <tr key={i} className="border-b border-gray-100" data-testid={`screening-hit-${i}`}>
                    <td className="py-2 font-medium">{h.matched_name}</td>
                    <td className="py-2"><span className="font-mono text-xs px-2 py-0.5 rounded-sm bg-red-50 text-red-700 border border-red-200">{h.type}</span></td>
                    <td className="py-2 text-gray-600 font-mono text-xs">{h.list}</td>
                  </tr>))}</tbody>
              </table>
            ) : a.status === "draft" ? <p className="text-sm text-gray-400">Jalankan submit untuk screening.</p> : <p className="text-sm text-emerald-600 flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> Tidak ada kecocokan pada watchlist.</p>}
          </div>

          {/* Company profile */}
          <div className="bg-white border border-gray-200 rounded-sm p-6">
            <h2 className="font-head font-bold flex items-center gap-2 mb-4"><Building2 className="w-4 h-4 text-gray-600" /> Profil Perusahaan</h2>
            <div className="grid sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
              <Info label="NIB" value={co.nib} mono />
              <Info label="NPWP" value={co.npwp} mono />
              <Info label="No. Akta" value={co.deed_number} mono />
              <Info label="Tahun Berdiri" value={co.established_year} mono />
              <Info label="Pendapatan Tahunan" value={rp(co.annual_revenue_idr)} mono />
              <Info label="Modal Disetor" value={rp(co.paid_up_capital_idr)} mono />
              <Info label="Volume Bulanan (est)" value={rp(co.expected_monthly_volume_idr)} mono />
              <Info label="Website" value={co.website} />
              <div className="sm:col-span-2"><Info label="Alamat" value={co.address} /></div>
              <div className="sm:col-span-2"><Info label="Sumber Dana" value={co.source_of_funds} /></div>
            </div>
          </div>

          {/* Directors */}
          <div className="bg-white border border-gray-200 rounded-sm p-6">
            <h2 className="font-head font-bold flex items-center gap-2 mb-4"><Users className="w-4 h-4 text-gray-600" /> Direksi & Beneficial Owner</h2>
            <div className="space-y-2">{(co.directors || []).map((d, i) => (
              <div key={i} className="flex items-center justify-between text-sm border-b border-gray-100 pb-2">
                <div><span className="font-medium">{d.name}</span> <span className="text-gray-400">· {d.role}</span></div>
                <div className="flex items-center gap-3 font-mono text-xs">
                  <span>{d.ownership_pct}%</span>
                  {d.is_pep && <span className="px-2 py-0.5 rounded-sm bg-amber-50 text-amber-700 border border-amber-200">PEP</span>}
                </div>
              </div>))}
            </div>
          </div>

          {/* Documents */}
          {a.documents?.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-sm p-6">
              <h2 className="font-head font-bold flex items-center gap-2 mb-4"><FileText className="w-4 h-4 text-gray-600" /> Dokumen</h2>
              <div className="divide-y">{a.documents.map((d) => (
                <div key={d.doc_id} className="py-2.5 flex items-center justify-between text-sm">
                  <span>{d.doc_type} · <span className="text-gray-400">{d.original_filename}</span></span>
                  <span className="text-xs text-gray-400 font-mono">{(d.size / 1024).toFixed(0)} KB</span>
                </div>))}
              </div>
            </div>
          )}

          {/* Decision */}
          {isOfficer && a.status === "under_review" && (
            <div className="bg-white border-2 border-blue-200 rounded-sm p-6">
              <h2 className="font-head font-bold mb-3">Keputusan Compliance Officer</h2>
              <Textarea data-testid="decision-note-input" value={note} onChange={(e) => setNote(e.target.value)} rows={2} className="rounded-sm mb-3" placeholder="Catatan keputusan (opsional)…" />
              <div className="flex gap-3">
                <Button data-testid="approve-button" onClick={() => decide("approved")} disabled={busy} className="rounded-sm bg-emerald-600 hover:bg-emerald-700 gap-2"><CheckCircle2 className="w-4 h-4" /> Setujui</Button>
                <Button data-testid="reject-button" onClick={() => decide("rejected")} disabled={busy} variant="outline" className="rounded-sm border-red-300 text-red-700 hover:bg-red-50 gap-2"><XCircle className="w-4 h-4" /> Tolak</Button>
              </div>
            </div>
          )}

          {a.decision && a.status !== "auto_rejected" && (
            <div className={`rounded-sm p-4 text-sm border ${a.decision === "approved" ? "bg-emerald-50 border-emerald-200 text-emerald-800" : "bg-red-50 border-red-200 text-red-800"}`}>
              Diputuskan <b>{a.decision === "approved" ? "DISETUJUI" : "DITOLAK"}</b> oleh {a.decided_by}. {a.decision_note && `— "${a.decision_note}"`}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Info({ label, value, mono }) {
  return (
    <div>
      <div className="text-xs text-gray-400 uppercase tracking-wider">{label}</div>
      <div className={`text-gray-900 ${mono ? "font-mono" : ""}`}>{value || "—"}</div>
    </div>
  );
}
