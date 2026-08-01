export function RiskBadge({ level }) {
  const map = {
    LOW: { c: "text-emerald-700 border-emerald-300 bg-emerald-50", t: "RISIKO RENDAH" },
    MEDIUM: { c: "text-amber-700 border-amber-300 bg-amber-50", t: "RISIKO SEDANG" },
    HIGH: { c: "text-red-700 border-red-300 bg-red-50", t: "RISIKO TINGGI" },
  };
  const s = map[level] || map.MEDIUM;
  return (
    <span data-testid="risk-badge" className={`font-mono text-[11px] font-semibold px-2 py-0.5 border rounded-sm ${s.c}`}>
      {s.t}
    </span>
  );
}

export function StatusBadge({ status }) {
  const map = {
    draft: { c: "text-gray-600 border-gray-300 bg-gray-50", t: "DRAFT" },
    under_review: { c: "text-blue-700 border-blue-300 bg-blue-50", t: "REVIEW" },
    approved: { c: "text-emerald-700 border-emerald-300 bg-emerald-50", t: "DISETUJUI" },
    rejected: { c: "text-red-700 border-red-300 bg-red-50", t: "DITOLAK" },
  };
  const s = map[status] || map.draft;
  return <span className={`font-mono text-[11px] font-semibold px-2 py-0.5 border rounded-sm ${s.c}`}>{s.t}</span>;
}

export function ScoreGauge({ score, size = 140 }) {
  const v = score ?? 0;
  const color = v >= 75 ? "#059669" : v >= 50 ? "#D97706" : "#DC2626";
  const r = size / 2 - 12;
  const circ = 2 * Math.PI * r;
  const off = circ * (1 - v / 100);
  return (
    <div className="relative inline-flex" style={{ width: size, height: size }} data-testid="score-gauge">
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#E5E7EB" strokeWidth="10" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="10"
          strokeDasharray={circ} strokeDashoffset={off} strokeLinecap="butt"
          style={{ transition: "stroke-dashoffset 0.8s ease" }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-mono text-3xl font-semibold" style={{ color }}>{v}</span>
        <span className="text-[10px] text-gray-500 tracking-wide">/ 100</span>
      </div>
    </div>
  );
}

export function FactorBar({ label, value }) {
  const color = value >= 75 ? "bg-emerald-500" : value >= 50 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="space-y-1">
      <div className="flex justify-between items-baseline">
        <span className="text-sm text-gray-600">{label}</span>
        <span className="font-mono text-sm font-semibold text-gray-900">{value}</span>
      </div>
      <div className="h-2 bg-gray-100 rounded-sm overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${value}%`, transition: "width 0.6s ease" }} />
      </div>
    </div>
  );
}
