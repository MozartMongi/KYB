import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, formatApiErrorDetail, formatAxiosError, rp } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { ArrowRight, ArrowLeft, Plus, Trash2, UploadCloud, Sparkles, Building2, Users, FileText, Send, Check, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { APPLICATIONS_QUERY_KEY, DASHBOARD_STATS_QUERY_KEY } from "@/lib/queryKeys";

const INDUSTRIES = ["crypto_exchange","money_services","forex","fintech","trading","real_estate","ecommerce","technology","consulting","retail","logistics","mining","manufacturing","other"];
const STEPS = [
  { n: 1, label: "Legalitas", icon: Building2 },
  { n: 2, label: "Direksi & UBO", icon: Users },
  { n: 3, label: "Keuangan", icon: FileText },
  { n: 4, label: "Dokumen", icon: UploadCloud },
];

const filled = (v) => String(v ?? "").trim().length > 0;
const ADDRESS_MIN = 7;
const ADDRESS_MAX = 100;

const addressLen = (address) => (address || "").trim().length;
const addressValid = (address) => {
  const len = addressLen(address);
  return len >= ADDRESS_MIN && len <= ADDRESS_MAX;
};

/** Mandatory fields per step — Lanjut stays disabled until these are complete. */
function stepComplete(step, c) {
  if (step === 1) {
    return filled(c.legal_name) && filled(c.nib) && filled(c.npwp) && addressValid(c.address);
  }
  if (step === 2) {
    return c.directors.length > 0 && c.directors.every((d) => filled(d.name));
  }
  if (step === 3) {
    return filled(c.bank_code) && filled(c.bank_account_number) && filled(c.bank_account_holder);
  }
  return true;
}

export default function NewApplication() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [step, setStep] = useState(1);
  const [appId, setAppId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [banks, setBanks] = useState([]);
  const [banksLoading, setBanksLoading] = useState(true);
  const [c, setC] = useState({
    legal_name: "", brand_name: "", entity_type: "PT", nib: "", npwp: "", deed_number: "",
    established_year: "", industry: "crypto_exchange", country: "Indonesia", address: "", website: "",
    annual_revenue_idr: "", paid_up_capital_idr: "", expected_monthly_volume_idr: "", source_of_funds: "",
    bank_name: "", bank_code: "", bank_account_number: "", bank_account_holder: "",
    directors: [{ name: "", role: "Direktur Utama", id_number: "", is_pep: false, ownership_pct: "" }],
  });
  const [docs, setDocs] = useState([]);
  const [bankOpen, setBankOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setBanksLoading(true);
      try {
        const { data } = await api.get("/banks/available");
        if (cancelled) return;
        const list = Array.isArray(data?.banks) ? data.banks : [];
        setBanks(list);
        if (data?.source === "fallback" && data?.message) {
          toast.message(data.message);
        }
      } catch (e) {
        if (!cancelled) {
          setBanks([]);
          toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Gagal memuat daftar bank");
        }
      } finally {
        if (!cancelled) setBanksLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const upd = (k) => (e) => setC({ ...c, [k]: e.target?.value ?? e });
  const updAddress = (e) => {
    const value = (e.target?.value ?? "").slice(0, ADDRESS_MAX);
    setC({ ...c, address: value });
  };
  const updDir = (i, k, v) => { const d = [...c.directors]; d[i][k] = v; setC({ ...c, directors: d }); };
  const addDir = () => setC({ ...c, directors: [...c.directors, { name: "", role: "Direktur", id_number: "", is_pep: false, ownership_pct: "" }] });
  const rmDir = (i) => setC({ ...c, directors: c.directors.filter((_, j) => j !== i) });

  const payload = () => ({
    ...c,
    established_year: c.established_year ? parseInt(c.established_year) : null,
    annual_revenue_idr: parseFloat(c.annual_revenue_idr) || 0,
    paid_up_capital_idr: parseFloat(c.paid_up_capital_idr) || 0,
    expected_monthly_volume_idr: parseFloat(c.expected_monthly_volume_idr) || 0,
    directors: c.directors.map((d) => ({ ...d, ownership_pct: parseFloat(d.ownership_pct) || 0 })),
  });

  const ensureApp = async () => {
    if (appId) { await api.put(`/applications/${appId}`, payload()); return appId; }
    const { data } = await api.post("/applications", payload());
    setAppId(data.id);
    return data.id;
  };

  const next = async () => {
    if (!stepComplete(step, c)) {
      toast.error("Lengkapi field wajib sebelum melanjutkan");
      return;
    }
    setBusy(true);
    try { await ensureApp(); setStep(step + 1); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const uploadDoc = async (docType, file) => {
    if (!file) return;
    const id = await ensureApp();
    const fd = new FormData();
    fd.append("doc_type", docType);
    fd.append("file", file);
    toast.loading("Mengunggah & menganalisa dokumen…", { id: "up" });
    try {
      const { data } = await api.post(`/applications/${id}/documents`, fd);
      setDocs([...docs, data]);
      const ex = data.extracted || {};
      if (ex.company_legal_name || ex.nib || ex.npwp) {
        setC((prev) => ({
          ...prev,
          legal_name: prev.legal_name || ex.company_legal_name || "",
          nib: prev.nib || ex.nib || "",
          npwp: prev.npwp || ex.npwp || "",
          deed_number: prev.deed_number || ex.deed_number || "",
        }));
        toast.success("AI mengekstrak data dari dokumen", { id: "up" });
      } else {
        toast.success("Dokumen terunggah", { id: "up" });
      }
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail), { id: "up" });
    }
  };

  const submit = async () => {
    if (!filled(c.nib)) {
      toast.error("NIB wajib diisi");
      return;
    }
    if (!addressValid(c.address)) {
      toast.error(`Alamat terdaftar harus ${ADDRESS_MIN}–${ADDRESS_MAX} karakter`);
      return;
    }
    setBusy(true);
    setSubmitting(true);
    try {
      const id = await ensureApp();
      toast.loading("Memverifikasi NPWP, rekening & NIB (OSS). Proses verifikasi sekitar 1–2 Menit...", { id: "sub" });
      // Browserbase OSS scrape often needs 30–90s; default axios timeout (20s) aborts early
      // and surfaces as a generic error even when the backend later succeeds.
      await api.post(`/applications/${id}/submit`, null, { timeout: 180000 });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: APPLICATIONS_QUERY_KEY }),
        queryClient.invalidateQueries({ queryKey: DASHBOARD_STATS_QUERY_KEY }),
      ]);
      toast.success("Aplikasi dikirim. Hasil verifikasi (termasuk NIB OSS) siap ditinjau.", { id: "sub" });
      navigate(`/applications/${id}`);
    } catch (e) {
      toast.error(formatAxiosError(e), { id: "sub" });
    } finally {
      setBusy(false);
      setSubmitting(false);
    }
  };

  // Portal to body: parent `.animate-fade-up` keeps a transform, which would otherwise
  // confine position:fixed to the main pane (sidebar + page bottom stay clickable).
  const submitBackdrop = submitting
    ? createPortal(
        <div
          data-testid="submit-backdrop"
          className="fixed inset-0 z-[100] bg-black/40"
          aria-hidden="true"
          onClick={(e) => e.stopPropagation()}
        />,
        document.body,
      )
    : null;

  return (
    <div className="animate-fade-up">
      {submitBackdrop}
      <header className="bg-white border-b border-gray-200 px-8 py-5">
        <h1 className="font-head font-extrabold text-2xl tracking-tight">Onboarding Nasabah Perusahaan</h1>
        <p className="text-sm text-gray-500">Verifikasi KYB berstandar perbankan dengan credit scoring</p>
      </header>

      <div className="p-8 max-w-4xl">
        {/* Stepper */}
        <div className="flex items-center mb-8">
          {STEPS.map((s, i) => {
            const Icon = s.icon;
            const active = step === s.n, done = step > s.n;
            return (
              <div key={s.n} className="flex items-center flex-1 last:flex-none">
                <div className="flex items-center gap-2">
                  <div className={`w-9 h-9 rounded-sm flex items-center justify-center border transition-colors duration-200 ${
                    done ? "bg-emerald-600 border-emerald-600 text-white" : active ? "bg-blue-600 border-blue-600 text-white" : "bg-white border-gray-300 text-gray-400"}`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <span className={`text-sm font-medium hidden sm:block ${active ? "text-gray-900" : "text-gray-400"}`}>{s.label}</span>
                </div>
                {i < STEPS.length - 1 && <div className={`flex-1 h-px mx-3 ${done ? "bg-emerald-600" : "bg-gray-200"}`} />}
              </div>
            );
          })}
        </div>

        <div className="bg-white border border-gray-200 rounded-sm p-6">
          {step === 1 && (
            <div className="grid sm:grid-cols-2 gap-4">
              <Field label="Nama Legal Perusahaan *"><Input data-testid="legal-name-input" value={c.legal_name} onChange={upd("legal_name")} className="rounded-sm" placeholder="PT Contoh Kripto Nusantara" /></Field>
              <Field label="Nama Merek / Brand"><Input value={c.brand_name} onChange={upd("brand_name")} className="rounded-sm" /></Field>
              <Field label="Jenis Entitas">
                <Select value={c.entity_type} onValueChange={(v) => setC({ ...c, entity_type: v })}>
                  <SelectTrigger className="rounded-sm" data-testid="entity-type-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{["PT","PT PMA","CV","Firma","Koperasi","Yayasan"].map((x) => <SelectItem key={x} value={x}>{x}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
              <Field label="Industri">
                <Select value={c.industry} onValueChange={(v) => setC({ ...c, industry: v })}>
                  <SelectTrigger className="rounded-sm" data-testid="industry-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{INDUSTRIES.map((x) => <SelectItem key={x} value={x}>{x.replace(/_/g, " ")}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
              <Field label="NIB *"><Input data-testid="nib-input" value={c.nib} onChange={upd("nib")} className="rounded-sm font-mono" placeholder="13 digit" required /></Field>
              <Field label="NPWP *"><Input data-testid="npwp-input" value={c.npwp} onChange={upd("npwp")} className="rounded-sm font-mono" placeholder="15–16 digit" /></Field>
              <Field label="No. Akta Pendirian"><Input value={c.deed_number} onChange={upd("deed_number")} className="rounded-sm font-mono" /></Field>
              <Field label="Tahun Berdiri"><Input type="number" value={c.established_year} onChange={upd("established_year")} className="rounded-sm font-mono" placeholder="2019" /></Field>
              <Field label="Website"><Input value={c.website} onChange={upd("website")} className="rounded-sm" /></Field>
              <Field label="Negara"><Input value={c.country} onChange={upd("country")} className="rounded-sm" /></Field>
              <div className="sm:col-span-2">
                <Field
                  label="Alamat Terdaftar *"
                  hint={`${addressLen(c.address)}/${ADDRESS_MAX} karakter · minimal ${ADDRESS_MIN}, maksimal ${ADDRESS_MAX}`}
                >
                  <Textarea
                    data-testid="address-input"
                    value={c.address}
                    onChange={updAddress}
                    className="rounded-sm"
                    rows={2}
                    minLength={ADDRESS_MIN}
                    maxLength={ADDRESS_MAX}
                    placeholder="Alamat kantor terdaftar perusahaan"
                  />
                </Field>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              {c.directors.map((d, i) => (
                <div key={i} className="border border-gray-200 rounded-sm p-4">
                  <div className="flex items-center justify-between mb-3">
                    <span className="font-head font-bold text-sm">Direktur / UBO #{i + 1}</span>
                    {c.directors.length > 1 && <button data-testid={`remove-director-${i}`} onClick={() => rmDir(i)} className="text-red-500 hover:text-red-700"><Trash2 className="w-4 h-4" /></button>}
                  </div>
                  <div className="grid sm:grid-cols-2 gap-3">
                    <Field label="Nama *"><Input data-testid={`director-name-${i}`} value={d.name} onChange={(e) => updDir(i, "name", e.target.value)} className="rounded-sm" /></Field>
                    <Field label="Jabatan"><Input value={d.role} onChange={(e) => updDir(i, "role", e.target.value)} className="rounded-sm" /></Field>
                    <Field label="No. Identitas (KTP/Paspor)"><Input value={d.id_number} onChange={(e) => updDir(i, "id_number", e.target.value)} className="rounded-sm font-mono" /></Field>
                    <Field label="Kepemilikan (%)"><Input type="number" value={d.ownership_pct} onChange={(e) => updDir(i, "ownership_pct", e.target.value)} className="rounded-sm font-mono" /></Field>
                    <label className="flex items-center gap-2 text-sm mt-1 sm:col-span-2">
                      <Checkbox data-testid={`director-pep-${i}`} checked={d.is_pep} onCheckedChange={(v) => updDir(i, "is_pep", !!v)} />
                      Politically Exposed Person (PEP) / berhubungan dengan pejabat publik
                    </label>
                  </div>
                </div>
              ))}
              <Button data-testid="add-director-button" variant="outline" onClick={addDir} className="rounded-sm gap-2"><Plus className="w-4 h-4" /> Tambah Direktur / UBO</Button>
            </div>
          )}

          {step === 3 && (
            <div className="grid sm:grid-cols-2 gap-4">
              <Field label="Pendapatan Tahunan (IDR)" hint={rp(c.annual_revenue_idr)}><Input data-testid="revenue-input" type="number" value={c.annual_revenue_idr} onChange={upd("annual_revenue_idr")} className="rounded-sm font-mono" /></Field>
              <Field label="Modal Disetor (IDR)" hint={rp(c.paid_up_capital_idr)}><Input data-testid="capital-input" type="number" value={c.paid_up_capital_idr} onChange={upd("paid_up_capital_idr")} className="rounded-sm font-mono" /></Field>
              <Field label="Estimasi Volume Bulanan (IDR)" hint={rp(c.expected_monthly_volume_idr)}><Input type="number" value={c.expected_monthly_volume_idr} onChange={upd("expected_monthly_volume_idr")} className="rounded-sm font-mono" /></Field>
              <div className="sm:col-span-2"><Field label="Sumber Dana"><Textarea value={c.source_of_funds} onChange={upd("source_of_funds")} className="rounded-sm" rows={2} placeholder="Contoh: modal pemegang saham, pendapatan operasional trading" /></Field></div>
              <div className="sm:col-span-2 border-t border-gray-200 pt-4 mt-1">
                <div className="font-head font-bold text-sm mb-3">Rekening Bank Perusahaan</div>
              </div>
              <Field label="Bank *">
                <Popover open={bankOpen} onOpenChange={setBankOpen}>
                  <PopoverTrigger asChild>
                    <Button
                      type="button"
                      variant="outline"
                      role="combobox"
                      aria-expanded={bankOpen}
                      data-testid="bank-code-select"
                      disabled={banksLoading || banks.length === 0}
                      className="w-full justify-between rounded-sm font-normal h-9 px-3"
                    >
                      <span className="truncate">
                        {banksLoading
                          ? "Memuat daftar bank…"
                          : c.bank_code
                            ? `${c.bank_name || banks.find((b) => b.code === c.bank_code)?.name || c.bank_code} (${c.bank_code})`
                            : "Cari atau pilih bank…"}
                      </span>
                      <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0 rounded-sm" align="start">
                    <Command>
                      <CommandInput placeholder="Cari nama atau kode bank…" className="h-9" />
                      <CommandList>
                        <CommandEmpty>Bank tidak ditemukan.</CommandEmpty>
                        <CommandGroup>
                          {banks.map((b) => (
                            <CommandItem
                              key={b.code}
                              value={`${b.name} ${b.code}`}
                              data-testid={`bank-option-${b.code}`}
                              onSelect={() => {
                                setC({ ...c, bank_code: b.code, bank_name: b.name });
                                setBankOpen(false);
                              }}
                            >
                              <Check className={cn("mr-2 h-4 w-4", c.bank_code === b.code ? "opacity-100" : "opacity-0")} />
                              <span className="truncate">{b.name}</span>
                              <span className="ml-auto pl-2 font-mono text-xs text-gray-400">{b.code}</span>
                            </CommandItem>
                          ))}
                        </CommandGroup>
                      </CommandList>
                    </Command>
                  </PopoverContent>
                </Popover>
              </Field>
              <Field label="Nomor Rekening *"><Input data-testid="bank-account-number-input" value={c.bank_account_number} onChange={upd("bank_account_number")} className="rounded-sm font-mono" /></Field>
              <div className="sm:col-span-2"><Field label="Nama Pemilik Rekening *" hint="Diverifikasi otomatis saat Kirim & Nilai Risiko"><Input data-testid="bank-account-holder-input" value={c.bank_account_holder} onChange={upd("bank_account_holder")} className="rounded-sm" placeholder="PT Contoh Kripto Nusantara" /></Field></div>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-sm text-blue-700 bg-blue-50 border border-blue-200 rounded-sm p-3">
                <Sparkles className="w-4 h-4" /> Unggah gambar dokumen (JPG/PNG) — AI akan mengekstrak data secara otomatis. Saat kirim, sistem memverifikasi NPWP, rekening bank & NIB via OSS, lalu menilai risiko.
              </div>
              <div className="grid sm:grid-cols-2 gap-3">
                {["Akta Pendirian","NIB","NPWP","KTP Direktur","Laporan Keuangan","Lainnya"].map((dt) => (
                  <label key={dt} data-testid={`upload-${dt}`} className="border border-dashed border-gray-300 rounded-sm p-4 flex items-center gap-3 cursor-pointer hover:border-blue-500 transition-colors duration-200">
                    <UploadCloud className="w-5 h-5 text-gray-400" />
                    <span className="text-sm text-gray-600">{dt}</span>
                    <input type="file" className="hidden" onChange={(e) => uploadDoc(dt, e.target.files[0])} />
                  </label>
                ))}
              </div>
              {docs.length > 0 && (
                <div className="border border-gray-200 rounded-sm divide-y">
                  {docs.map((d) => (
                    <div key={d.doc_id} className="px-4 py-2.5 flex items-center justify-between text-sm">
                      <span><FileText className="w-4 h-4 inline mr-2 text-gray-400" />{d.doc_type} · <span className="text-gray-400">{d.original_filename}</span></span>
                      {d.extracted && (d.extracted.nib || d.extracted.company_legal_name) && <span className="text-xs text-emerald-600 flex items-center gap-1"><Sparkles className="w-3 h-3" /> diekstrak</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="flex justify-between mt-8 pt-5 border-t border-gray-200">
            <Button data-testid="prev-step-button" variant="outline" onClick={() => setStep(Math.max(1, step - 1))} disabled={step === 1} className="rounded-sm gap-2"><ArrowLeft className="w-4 h-4" /> Kembali</Button>
            {step < 4 ? (
              <Button data-testid="next-step-button" onClick={next} disabled={busy || !stepComplete(step, c)} className="rounded-sm bg-black hover:bg-gray-800 gap-2">Lanjut <ArrowRight className="w-4 h-4" /></Button>
            ) : (
              <Button data-testid="submit-application-button" onClick={submit} disabled={busy || submitting} className="rounded-sm bg-blue-600 hover:bg-blue-700 gap-2"><Send className="w-4 h-4" /> Kirim & Nilai Risiko</Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-sm">{label}</Label>
      {children}
      {hint && <div className="text-xs text-gray-400 font-mono">{hint}</div>}
    </div>
  );
}
