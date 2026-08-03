import axios from "axios";

// Prefer env backend URL; fall back to same-origin `/api` (Vercel rewrites / proxy).
// Avoids CORS when frontend & backend share a host; keeps cross-origin for split deploy.
const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
export const API = BACKEND_URL ? `${BACKEND_URL}/api` : "/api";

export const api = axios.create({ baseURL: API, withCredentials: true });

export function formatApiErrorDetail(detail) {
  if (detail == null) return "Terjadi kesalahan. Silakan coba lagi.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).filter(Boolean).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export const rp = (n) => {
  if (!n) return "Rp 0";
  return "Rp " + Number(n).toLocaleString("id-ID");
};
