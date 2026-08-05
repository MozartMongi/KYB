import axios from "axios";

/**
 * Resolve API base URL.
 *
 * Hosted monorepos (Vercel services + rewrites, Emergent preview) serve the SPA and
 * FastAPI under the same origin: `/api/*` is rewritten to the backend. Calling that
 * path avoids cross-origin requests entirely (the "CORS" errors after ~30s are almost
 * always timed-out cross-origin calls with no response headers).
 *
 * Use an absolute REACT_APP_BACKEND_URL only when the API is truly on another origin
 * (e.g. local CRA on :3000 talking to uvicorn on :8000).
 */
function resolveApiBase() {
  let envBackend = (process.env.REACT_APP_BACKEND_URL || "").trim();
  envBackend = envBackend.replace(/\/$/, "").replace(/\/api$/i, "");

  if (!envBackend) return "/api";

  if (typeof window !== "undefined") {
    try {
      if (new URL(envBackend).origin === window.location.origin) {
        return "/api";
      }
    } catch {
      return "/api";
    }
  }

  return `${envBackend}/api`;
}

export const API = resolveApiBase();

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
  timeout: 20000,
});

/**
 * Session cookies are `Secure; SameSite=None`, so browsers silently drop them on
 * non-HTTPS origins and under third-party cookie blocking (Safari ITP). The backend
 * also accepts `Authorization: Bearer <token>`, so keep the token as a fallback —
 * otherwise the session only lives in React state and is lost on the next page load.
 */
const TOKEN_KEY = "corpscore.auth_token";

export function getAuthToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setAuthToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage disabled (private mode) — cookie auth still applies */
  }
}

export function clearAuthToken() {
  setAuthToken("");
}

api.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) {
    config.headers = config.headers || {};
    if (!config.headers.Authorization) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export function formatApiErrorDetail(detail) {
  if (detail == null) return "Terjadi kesalahan. Silakan coba lagi.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).filter(Boolean).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

/** Prefer this in UI catch blocks — network timeouts often surface as fake "CORS" errors. */
export function formatAxiosError(err) {
  const detail = err?.response?.data?.detail;
  if (detail != null) return formatApiErrorDetail(detail);

  if (err?.code === "ECONNABORTED" || /timeout/i.test(err?.message || "")) {
    return "Server terlalu lama merespons. Coba lagi sebentar.";
  }

  // No response body: connection reset, cold-start kill, DNS, or opaque CORS fail.
  if (!err?.response) {
    return "Tidak dapat terhubung ke API. Pastikan backend berjalan dan request memakai same-origin /api.";
  }

  return err.message || "Terjadi kesalahan. Silakan coba lagi.";
}

export const rp = (n) => {
  if (!n) return "Rp 0";
  return "Rp " + Number(n).toLocaleString("id-ID");
};
