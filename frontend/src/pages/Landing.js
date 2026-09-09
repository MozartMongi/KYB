import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { HOME } from "@/constants/testIds";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  SheetClose,
} from "@/components/ui/sheet";
import {
  ShieldCheck,
  ArrowRight,
  ArrowDownRight,
  Menu,
  Building2,
  FileSearch,
  Scale,
  ScanSearch,
  Landmark,
  Sparkles,
  Clock,
  CheckCircle2,
  FileText,
  Users,
  Mail,
} from "lucide-react";

const NAV_LINKS = [
  { href: "#beranda", label: "Beranda" },
  { href: "#tentang", label: "Tentang" },
  { href: "#layanan", label: "Layanan" },
  { href: "#alur", label: "Alur kerja" },
  { href: "#faq", label: "FAQ" },
];

const TICKER = [
  "Onboarding standar perbankan",
  "Verifikasi NIB OSS",
  "Screening PEP & sanksi",
  "Credit scoring transparan",
  "Aligned PPATK",
  "Ekstraksi dokumen AI",
  "SLA 3 hari kerja",
  "KYC direksi & UBO",
];

const STATS = [
  { value: "4", label: "Faktor skor kredit yang transparan — legalitas, keuangan, screening AML, dan industri." },
  { value: "3", label: "Hari kerja SLA review compliance untuk keputusan onboarding yang terukur." },
  { value: "AI", label: "Ekstraksi dokumen otomatis untuk mempercepat kelengkapan berkas KYB." },
];

const SERVICES = [
  {
    n: "01",
    icon: Building2,
    title: "Onboarding KYB",
    body: "Wizard onboarding 4 langkah dengan standar perbankan: legalitas, direksi & UBO, keuangan, dan unggah dokumen — dirancang untuk nasabah perusahaan dan prioritas exchange kripto.",
  },
  {
    n: "02",
    icon: Scale,
    title: "Credit scoring",
    body: "Penilaian risiko 0–100 dengan bobot yang jelas: Legalitas 25%, Keuangan 25%, Screening AML 30%, Industri 20%, plus penyesuaian AI. Level risiko LOW / MEDIUM / HIGH.",
  },
  {
    n: "03",
    icon: ScanSearch,
    title: "Screening AML",
    body: "Pemeriksaan PEP, sanksi, dan adverse media pada nama perusahaan serta pengendali. Hasil screening masuk ke antrean review compliance bersama skor risiko.",
  },
];

const CAPABILITIES = [
  { icon: FileSearch, title: "Verifikasi NIB", body: "Cek NIB terhadap data OSS, termasuk penolakan otomatis jika masa berlaku sudah habis." },
  { icon: Landmark, title: "Cek rekening bank", body: "Pencocokan nama rekening dengan nama legal perusahaan sebelum onboarding dilanjutkan." },
  { icon: Sparkles, title: "Ekstraksi dokumen AI", body: "Unggah akta, NIB, NPWP, dan identitas — field penting diekstrak untuk mempercepat review." },
  { icon: FileText, title: "Laporan PDF", body: "Ekspor laporan risiko lengkap: profil, skor, screening, dan keputusan — siap untuk arsip compliance." },
  { icon: Users, title: "KYC per UBO", body: "Verifikasi identitas direksi dan pemilik manfaat akhir secara terpisah dari sesi KYB perusahaan." },
  { icon: Clock, title: "Antrean SLA", body: "Dashboard compliance dengan target 3 hari kerja, penanda overdue, dan jejak keputusan." },
];

const STEPS = [
  { n: "01", title: "Legalitas", body: "Isi nama legal, NIB, NPWP, akta, dan alamat perusahaan." },
  { n: "02", title: "Direksi & UBO", body: "Daftarkan pengendali, kepemilikan, dan status PEP." },
  { n: "03", title: "Keuangan & bank", body: "Lengkapi pendapatan, modal, dan rekening untuk verifikasi." },
  { n: "04", title: "Dokumen & review", body: "Unggah berkas, kirim, lalu pantau skor dan keputusan compliance." },
];

const FAQS = [
  {
    q: "Apa itu CorpScore?",
    a: "CorpScore adalah platform KYB (Know Your Business) dan credit scoring untuk onboarding nasabah perusahaan serta prioritas pada crypto exchange di Indonesia. Pendekatan kami mengikuti alur KYB perbankan: verifikasi legalitas, screening AML, dan penilaian risiko yang dapat diaudit.",
  },
  {
    q: "Siapa yang menggunakan platform ini?",
    a: "Compliance officer meninjau, menilai, dan memutuskan aplikasi. Calon nasabah perusahaan mengisi wizard onboarding, mengunggah dokumen, lalu memantau status pengajuan mereka sendiri.",
  },
  {
    q: "Dokumen apa yang perlu disiapkan?",
    a: "Umumnya NIB, NPWP, akta pendirian/perubahan, data direksi & UBO, serta bukti rekening perusahaan. Sistem membantu mengekstrak field dari dokumen yang diunggah agar review lebih cepat.",
  },
  {
    q: "Bagaimana skor kredit dihitung?",
    a: "Skor 0–100 disusun dari empat faktor: Legalitas 25%, Keuangan 25%, Screening AML 30%, dan Industri 20%. Penyesuaian AI dapat menambah konteks kualitatif (±15) tanpa menghilangkan rincian bobot di konsol.",
  },
  {
    q: "Berapa lama proses review?",
    a: "Target SLA review compliance adalah 3 hari kerja setelah pengajuan lengkap. Dashboard menandai kasus yang mendekati atau melewati batas waktu agar antrean tetap terukur.",
  },
  {
    q: "Apakah selaras dengan regulasi Indonesia?",
    a: "Alur dirancang selaras praktik KYB/AML untuk exchange di Indonesia, termasuk verifikasi NIB OSS dan kerangka screening PEP/sanksi. Keputusan akhir tetap pada kebijakan compliance institusi Anda.",
  },
];

function BrandMark({ light = false }) {
  return (
    <Link to="/" className="flex items-center gap-2.5" data-testid={HOME.logo}>
      <div className="w-8 h-8 rounded-sm bg-blue-600 flex items-center justify-center">
        <ShieldCheck className="w-5 h-5 text-white" />
      </div>
      <div className="leading-tight">
        <div className={`font-head font-extrabold tracking-tight ${light ? "text-white" : "text-[#0A0A0A]"}`}>
          CorpScore
        </div>
        <div className={`text-[10px] tracking-widest ${light ? "text-gray-400" : "text-gray-500"}`}>
          KYB & Credit Scoring
        </div>
      </div>
    </Link>
  );
}

function AuthButton({ user, className = "" }) {
  const navigate = useNavigate();
  const to = user ? "/dashboard" : "/login";
  const label = user ? "Dashboard" : "Login";
  return (
    <button
      type="button"
      data-testid={HOME.loginButton}
      onClick={() => navigate(to)}
      className={`inline-flex items-center justify-center gap-2 rounded-sm bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 transition-colors duration-200 ${className}`}
    >
      {label} <ArrowRight className="w-4 h-4" />
    </button>
  );
}

export default function Landing() {
  const { user } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    document.documentElement.classList.add("scroll-smooth");
    return () => document.documentElement.classList.remove("scroll-smooth");
  }, []);

  return (
    <div className="min-h-screen bg-[#F8F9FA] text-[#111827]" data-testid={HOME.page}>
      {/* Top announcement — hosting-style bar, CorpScore palette */}
      <div className="bg-[#2663ec] text-xs">
        <div className="max-w-6xl mx-auto px-5 py-2.5 flex items-center justify-between gap-4">
          <p className="text-gray-300 truncate">
            KYB & risk management score untuk crypto exchange Indonesia — standar onboarding perbankan.
          </p>
          <a href="mailto:corporate@corpscore.tech" className="hidden sm:inline-flex items-center gap-1.5 text-gray-400 hover:text-white shrink-0">
            <Mail className="w-3.5 h-3.5" /> corporate@corpscore.tech
          </a>
        </div>
      </div>

      <header className="sticky top-0 z-40 bg-white/95 backdrop-blur border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-5 h-16 flex items-center justify-between gap-4">
          <BrandMark />
          <nav className="hidden lg:flex items-center gap-8 text-sm text-gray-600">
            {NAV_LINKS.map((l) => (
              <a key={l.href} href={l.href} className="hover:text-[#0A0A0A] transition-colors duration-200">
                {l.label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <AuthButton user={user} />
            <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
              <SheetTrigger asChild>
                <button
                  type="button"
                  data-testid={HOME.menuButton}
                  className="lg:hidden w-9 h-9 rounded-sm border border-gray-200 flex items-center justify-center text-[#0A0A0A] hover:bg-gray-50"
                  aria-label="Buka menu"
                >
                  <Menu className="w-4 h-4" />
                </button>
              </SheetTrigger>
              <SheetContent side="right" className="rounded-none w-72">
                <SheetHeader>
                  <SheetTitle className="font-head text-left">Menu</SheetTitle>
                </SheetHeader>
                <nav className="mt-6 flex flex-col gap-1">
                  {NAV_LINKS.map((l) => (
                    <SheetClose asChild key={l.href}>
                      <a href={l.href} className="px-3 py-2.5 rounded-sm text-sm hover:bg-gray-100">
                        {l.label}
                      </a>
                    </SheetClose>
                  ))}
                </nav>
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </header>

      {/* Hero — marketing-strategy split layout */}
      <section id="beranda" className="relative overflow-hidden scroll-mt-28">
        <div className="max-w-6xl mx-auto px-5 pt-16 pb-20 lg:pt-24 lg:pb-28 grid lg:grid-cols-12 gap-10 items-center">
          <div className="lg:col-span-7 relative z-10">
            <h1 className="font-head font-extrabold text-4xl sm:text-5xl lg:text-[3.4rem] leading-[1.08] tracking-tight text-[#0A0A0A]">
              Kami mengamankan onboarding bisnis untuk exchange Anda.
            </h1>
          </div>
          <div className="lg:col-span-5 relative z-10">
            <div className="flex items-center gap-3">
              <img
                src={`${process.env.PUBLIC_URL}/speedometer.png`}
                alt=""
                className="w-12 h-12 rounded-sm object-contain shrink-0"
              />
              <div>
                <div className="font-head font-extrabold text-lg leading-tight">Faktor Skor Manajemen Risiko</div>
                <div className="text-xs text-gray-500">Legalitas · Keuangan · AML · Industri</div>
              </div>
            </div>
            <div className="h-px bg-gray-200 my-5" />
            <p className="text-gray-600 leading-relaxed">
              Onboarding nasabah perusahaan & prioritas dengan standar perbankan — verifikasi dokumen berbasis AI,
              screening PEP/sanksi, dan penilaian risiko kredit yang transparan.
            </p>
            <Link
              to="/login"
              data-testid={HOME.heroCta}
              className="mt-7 inline-flex items-center gap-2 rounded-sm bg-[#0A0A0A] hover:bg-gray-800 text-white px-5 py-3 text-sm font-medium transition-colors duration-200"
            >
              Masuk ke konsol <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>

        <div className="pointer-events-none absolute inset-y-8 right-[8%] hidden xl:block w-72 h-72 opacity-40">
          <div
            className="landing-sweep absolute inset-4 rounded-full"
            style={{
              background:
                "conic-gradient(from 0deg, rgba(37,99,235,0) 0deg, rgba(37,99,235,0.22) 80deg, rgba(37,99,235,0) 150deg)",
            }}
          />
          <div className="landing-radiate absolute inset-0 rounded-full border border-gray-300" />
          <div className="landing-radiate absolute inset-8 rounded-full border border-blue-400/50 [animation-delay:1.6s]" />
          <div className="landing-radiate absolute inset-16 rounded-full border border-gray-300 [animation-delay:3.2s]" />
          <div className="absolute inset-0 flex items-center justify-center">
            <ShieldCheck className="landing-breathe w-16 h-16 text-blue-600/40" />
          </div>
        </div>
      </section>

      {/* Trust bar */}
      <div className="border-y border-gray-200 bg-white">
        <div className="max-w-6xl mx-auto px-5 py-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3 text-sm text-gray-700">
            <span className="w-8 h-8 rounded-sm bg-blue-600 text-white flex items-center justify-center shrink-0">
              <ArrowDownRight className="w-4 h-4" />
            </span>
            Platform KYB exchange kripto Indonesia — dibangun untuk tim compliance.
          </div>
          <div className="flex gap-6 font-mono text-xs text-gray-500">
            <div><span className="block text-lg font-semibold text-[#0A0A0A]">PPATK</span>Aligned</div>
            <div><span className="block text-lg font-semibold text-[#0A0A0A]">NIB</span>OSS check</div>
            <div><span className="block text-lg font-semibold text-[#0A0A0A]">SLA</span>3 hari kerja</div>
          </div>
        </div>
      </div>

      {/* Ticker — marketing-strategy strip */}
      <div className="bg-[#0A0A0A] text-white overflow-hidden grain">
        <div className="landing-marquee flex w-max py-4 text-sm tracking-wide">
          {[0, 1].map((copy) => (
            <div key={copy} className="flex items-center">
              {TICKER.map((item) => (
                <span key={`${copy}-${item}`} className="flex items-center gap-4 px-4 text-gray-200">
                  {item}
                  <span className="text-blue-500">✧</span>
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* Philosophy — marketing-strategy two-column */}
      <section id="tentang" className="max-w-6xl mx-auto px-5 py-20 lg:py-28 scroll-mt-28">
        <div className="grid lg:grid-cols-2 gap-8 items-stretch">
          <div className="relative min-h-[280px] overflow-hidden rounded-sm bg-[#0A0A0A] grain">
            <img
              src={`${process.env.PUBLIC_URL}/digital-compliance.jpeg`}
              alt=""
              className="absolute inset-0 w-full h-full object-cover opacity-40"
            />
            <div className="relative p-8 h-full flex flex-col justify-end text-white min-h-[280px]">
              <span className="self-start text-[10px] font-mono tracking-widest uppercase border border-white/30 px-3 py-1 rounded-sm">
                Digital compliance
              </span>
              <h3 className="font-head font-extrabold text-2xl mt-4 max-w-sm leading-snug">
                Filosofi kami: menggabungkan standar perbankan dengan kecepatan onboarding digital.
              </h3>
            </div>
          </div>
          <div className="bg-white border border-gray-200 rounded-sm p-8 lg:p-10 flex flex-col justify-center">
            <span className="self-start text-[10px] font-mono tracking-widest uppercase border border-gray-300 text-gray-500 px-3 py-1 rounded-sm">
              Tentang CorpScore
            </span>
            <h2 className="font-head font-extrabold text-3xl tracking-tight mt-4 text-[#0A0A0A]">
              Solusi KYB yang cerdas untuk pertumbuhan exchange yang patuh.
            </h2>
            <p className="mt-4 text-gray-600 leading-relaxed">
              Kami menyediakan onboarding Know Your Business berbasis data untuk crypto exchange di Indonesia.
              Dari verifikasi NIB dan rekening, screening PEP/sanksi, hingga skor kredit yang dapat dijelaskan —
              CorpScore membantu tim compliance memutuskan dengan cepat tanpa mengorbankan ketelitian.
            </p>
            <a href="#layanan" className="mt-6 inline-flex items-center gap-2 text-sm font-medium text-blue-600 hover:text-blue-700">
              Lihat layanan <ArrowRight className="w-4 h-4" />
            </a>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="max-w-6xl mx-auto px-5 pb-8">
        <div className="grid md:grid-cols-3 gap-10 md:gap-8 py-4">
          {STATS.map((s) => (
            <div key={s.value}>
              <div className="font-head font-extrabold text-5xl tracking-tight text-[#0A0A0A]">{s.value}</div>
              <p className="mt-3 text-sm text-gray-600 leading-relaxed">{s.label}</p>
            </div>
          ))}
        </div>
        <div className="mt-10 h-px bg-gray-200" />
        <div className="flex items-start justify-between gap-6 py-8">
          <p className="max-w-3xl text-lg text-gray-700 leading-relaxed">
            Kami membantu exchange dan nasabah perusahaan mengendalikan risiko onboarding — agar pertumbuhan bisnis
            tetap selaras dengan kewajiban AML/KYB.
          </p>
          <ArrowDownRight className="w-8 h-8 text-blue-600 shrink-0 hidden sm:block" />
        </div>
      </section>

      {/* Services numbered — marketing 01/02/03 */}
      <section id="layanan" className="bg-white border-y border-gray-200 scroll-mt-28">
        <div className="max-w-6xl mx-auto px-5 py-20 lg:py-24">
          <p className="text-[11px] font-mono tracking-widest uppercase text-blue-600">Solusi strategis</p>
          <h2 className="font-head font-extrabold text-3xl tracking-tight mt-2 mb-12">Layanan KYB & scoring</h2>
          <div className="space-y-0">
            {SERVICES.map((s, i) => {
              const Icon = s.icon;
              return (
                <div
                  key={s.n}
                  className={`grid lg:grid-cols-12 gap-6 py-10 ${i < SERVICES.length - 1 ? "border-b border-gray-200" : ""}`}
                >
                  <div className="lg:col-span-1 font-mono text-sm text-gray-400">{s.n}</div>
                  <div className="lg:col-span-4 flex items-start gap-3">
                    <span className="w-9 h-9 rounded-sm bg-[#0A0A0A] text-white flex items-center justify-center shrink-0">
                      <Icon className="w-4 h-4" />
                    </span>
                    <h3 className="font-head font-extrabold text-2xl tracking-tight">{s.title}</h3>
                  </div>
                  <div className="lg:col-span-7">
                    <p className="text-gray-600 leading-relaxed max-w-xl">{s.body}</p>
                    <Link to="/login" className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-blue-600 hover:text-blue-700">
                      Mulai di konsol <ArrowRight className="w-4 h-4" />
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Capability grid — hosting services cards */}
      <section className="max-w-6xl mx-auto px-5 py-20 lg:py-24">
        <p className="text-[11px] font-mono tracking-widest uppercase text-blue-600">Yang kami tawarkan</p>
        <h2 className="font-head font-extrabold text-3xl tracking-tight mt-2 mb-10">Kapabilitas platform</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {CAPABILITIES.map((c) => {
            const Icon = c.icon;
            return (
              <div key={c.title} className="bg-white border border-gray-200 rounded-sm p-6 hover:border-blue-500/40 transition-colors duration-200">
                <Icon className="w-5 h-5 text-blue-600" />
                <h3 className="font-head font-bold mt-4">{c.title}</h3>
                <p className="text-sm text-gray-600 mt-2 leading-relaxed">{c.body}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* How it works — hosting numbered steps */}
      <section id="alur" className="bg-[#0A0A0A] text-white grain scroll-mt-28">
        <div className="relative max-w-6xl mx-auto px-5 py-20 lg:py-24">
          <p className="text-[11px] font-mono tracking-widest uppercase text-blue-400">Sederhana & terukur</p>
          <h2 className="font-head font-extrabold text-3xl tracking-tight mt-2">Alur kerja onboarding</h2>
          <p className="mt-3 text-gray-400 max-w-xl">
            Empat langkah yang sama dengan wizard di konsol — dari legalitas hingga keputusan compliance.
          </p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-8 mt-12">
            {STEPS.map((s) => (
              <div key={s.n}>
                <div className="font-mono text-blue-400 text-sm mb-3">{s.n}</div>
                <h3 className="font-head font-bold text-lg">{s.title}</h3>
                <p className="text-sm text-gray-400 mt-2 leading-relaxed">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Score breakdown strip */}
      <section className="max-w-6xl mx-auto px-5 py-16">
        <div className="bg-white border border-gray-200 rounded-sm p-8 lg:p-10">
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 mb-8">
            <div>
              <p className="text-[11px] font-mono tracking-widest uppercase text-blue-600">Transparan</p>
              <h2 className="font-head font-extrabold text-2xl tracking-tight mt-1">Bobot skor yang dapat diaudit</h2>
            </div>
            <p className="text-sm text-gray-500 max-w-md">Setiap keputusan menampilkan rincian faktor — bukan skor kotak hitam.</p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              { pct: "25%", name: "Legalitas", items: "NIB, NPWP, akta, kelengkapan dokumen" },
              { pct: "25%", name: "Keuangan", items: "Pendapatan, modal, volume, rekening" },
              { pct: "30%", name: "Screening AML", items: "PEP, sanksi, adverse media" },
              { pct: "20%", name: "Industri", items: "Sektor, yurisdiksi, profil risiko" },
            ].map((f) => (
              <div key={f.name} className="border-t-2 border-blue-600 pt-4">
                <div className="font-mono text-2xl font-semibold text-[#0A0A0A]">{f.pct}</div>
                <div className="font-head font-bold mt-1">{f.name}</div>
                <p className="text-xs text-gray-500 mt-1">{f.items}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ — hosting two-column */}
      <section id="faq" className="bg-white border-y border-gray-200 scroll-mt-28">
        <div className="max-w-6xl mx-auto px-5 py-20 lg:py-24 grid lg:grid-cols-12 gap-10">
          <div className="lg:col-span-4">
            <p className="text-[11px] font-mono tracking-widest uppercase text-blue-600">Punya pertanyaan?</p>
            <h2 className="font-head font-extrabold text-3xl tracking-tight mt-2">Jawaban singkat seputar layanan kami.</h2>
            <p className="mt-4 text-sm text-gray-600">
              Tidak menemukan yang Anda cari? Hubungi{" "}
              <a href="mailto:corporate@corpscore.tech" className="text-blue-600 hover:underline">corporate@corpscore.tech</a>
            </p>
          </div>
          <div className="lg:col-span-8">
            <Accordion type="single" collapsible defaultValue="item-0" className="w-full">
              {FAQS.map((f, i) => (
                <AccordionItem key={f.q} value={`item-${i}`} className="border-gray-200">
                  <AccordionTrigger className="font-head text-base hover:no-underline" data-testid={`${HOME.faqItem}-${i}`}>
                    {f.q}
                  </AccordionTrigger>
                  <AccordionContent className="text-gray-600 leading-relaxed">{f.a}</AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>
        </div>
      </section>

      {/* CTA banner — hosting bottom CTA */}
      <section className="max-w-6xl mx-auto px-5 py-16 lg:py-20">
        <div className="relative overflow-hidden rounded-sm bg-[#0A0A0A] text-white px-8 py-12 lg:px-14 lg:py-16 grain">
          <div className="relative flex flex-col lg:flex-row lg:items-center justify-between gap-8">
            <div>
              <h2 className="font-head font-extrabold text-3xl tracking-tight mt-2 max-w-lg">
                Bawa onboarding perusahaan ke konsol compliance CorpScore.
              </h2>
            </div>
            <Link
              to="/login"
              className="inline-flex items-center gap-2 rounded-sm bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 text-sm font-medium shrink-0 transition-colors duration-200"
            >
              Login <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      <footer className="bg-[#0A0A0A] text-white">
        <div className="max-w-6xl mx-auto px-5 py-14 grid sm:grid-cols-2 lg:grid-cols-4 gap-10">
          <div className="lg:col-span-1">
            <BrandMark light />
            <p className="mt-4 text-sm text-gray-400 leading-relaxed">
              KYB & risk management score untuk crypto exchange Indonesia.
            </p>
          </div>
          <div>
            <h4 className="font-head font-bold text-sm mb-4">Perusahaan</h4>
            <ul className="space-y-2 text-sm text-gray-400">
              <li><a href="#tentang" className="hover:text-white">Tentang</a></li>
              <li><a href="#layanan" className="hover:text-white">Layanan</a></li>
              <li><a href="#faq" className="hover:text-white">FAQ</a></li>
            </ul>
          </div>
          <div>
            <h4 className="font-head font-bold text-sm mb-4">Konsol</h4>
            <ul className="space-y-2 text-sm text-gray-400">
              <li><Link to="/login" className="hover:text-white">Login</Link></li>
              <li><Link to="/login" className="hover:text-white">Daftar</Link></li>
              {user ? <li><Link to="/dashboard" className="hover:text-white">Dashboard</Link></li> : null}
            </ul>
          </div>
          <div>
            <h4 className="font-head font-bold text-sm mb-4">Kontak</h4>
            <ul className="space-y-2 text-sm text-gray-400">
              <li>
                <a href="mailto:corporate@corpscore.tech" className="hover:text-white">corporate@corpscore.tech</a>
              </li>
              <li>Indonesia</li>
            </ul>
          </div>
        </div>
        <div className="border-t border-white/10">
          <div className="max-w-6xl mx-auto px-5 py-5 flex flex-col sm:flex-row justify-between gap-2 text-xs text-gray-500 font-mono">
            <span>© 2026 CorpScore</span>
            <span className="flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5 text-blue-500" /> Confidential compliance workspace</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
