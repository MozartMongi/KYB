# CorpScore — KYB & Credit Scoring for Indonesian Crypto Exchange

## Original Problem Statement
Build a KYB (Know Your Business) tool for crypto exchange corporate/priority customers in Indonesia (like SUMSUB, Binderr), using a banking-style KYB onboarding approach with credit scoring as the fundamental basis.

## Architecture
- **Backend**: FastAPI + MongoDB (motor). All routes under `/api`.
- **Frontend**: React 19 + Tailwind + shadcn/ui, Manrope/IBM Plex fonts, Swiss high-contrast RegTech aesthetic.
- **Auth**: Email/password JWT (httpOnly cookie `access_token`) + Emergent-managed Google OAuth (`session_token`). RBAC: `owner`/`officer` (compliance) vs `applicant`.
- **AI**: Emergent LLM key, OpenAI gpt-5.4 — document field extraction (image OCR) + qualitative AML/KYB risk review (narrative, red flags, recommended EDD).
- **Storage**: Emergent object storage for KYB document uploads.

## User Personas
- **Compliance Officer / Owner** (rizkyjo@pegasusexchange.id): reviews all applications, sees risk scores, approves/rejects.
- **Applicant (corporate customer)**: submits company KYB via wizard, tracks own applications only.

## Core Requirements (static)
- Corporate onboarding wizard: legality (NIB/NPWP/akta/entity), directors & UBO (with PEP flag), financials, document uploads with AI extraction.
- Transparent credit/risk scoring: rule-based factors — Legality 25%, Financial 25%, Screening/AML 30%, Industry 20% — plus AI adjustment (±15). Risk level LOW/MEDIUM/HIGH.
- AML/PEP/sanctions watchlist screening (mock watchlist for demo).
- Compliance dashboard: stats, review queue table, case detail, approve/reject with note.

## Implemented (2026-08-01)
- ✅ JWT email/password auth + Emergent Google login, seeded owner account, RBAC.
- ✅ 4-step onboarding wizard with AI document extraction (image mimetypes).
- ✅ Rule-based + AI hybrid scoring engine with transparent factor breakdown + score gauge.
- ✅ Mock watchlist screening (PEP self-declared + sanction/PEP/adverse-media name matching).
- ✅ Compliance dashboard (stats + review queue) and case detail (score, factors, AI analysis, screening hits, profile, directors, documents, decision).
- ✅ Object storage document upload + access-controlled download.
- ✅ NIB verification with auto-rejection when expiry date has passed (status `auto_rejected` + reason).
- ✅ Bank account verification (name-match vs company name, masked account number).
- ✅ Manual admin review queue with 3 business-day SLA target (`sla_due_at`), SLA column + overdue highlight on dashboard.
- ✅ Re-submission guard on finalized applications (auto_rejected/approved/rejected → 400).
- ✅ Tested: iteration_1 (core) + iteration_2 (NIB/bank/SLA/auto-reject) both 100% on new suites.

## MOCKED
- **AML/PEP/sanctions watchlist screening** uses an in-code `MOCK_WATCHLIST` (not a real screening provider). Real provider integration is a P1 backlog item.

## Backlog
- **P1**: Integrate real sanctions/PEP screening provider (e.g. Dow Jones, ComplyAdvantage) replacing MOCK_WATCHLIST.
- **P1**: Document viewer/preview in case detail; PDF AI extraction (currently images only).
- **P2**: Audit log & case notes history; export KYB report as PDF.
- **P2**: Ongoing monitoring / periodic re-screening; email notifications on decision.
- **P2**: Configurable scoring weights per compliance policy.

## Next Tasks
- Real screening provider integration; document preview; PDF export of the risk report.

## Didit KYC/KYB Integration (2026-08-01)
- Integrated Didit hosted verification (https://docs.didit.me): `POST /v3/session/` (create) + `GET /v3/session/{id}/decision/` (retrieve), `x-api-key` auth, KYB via workflow_id.
- Backend: `didit_create_session()` / `didit_get_decision()` (env-gated), endpoints `POST /api/applications/{id}/didit/session` and `GET /api/applications/{id}/didit/decision`.
- Frontend: "Verifikasi Didit (KYC/KYB)" card in case detail — create hosted session (opens verification URL), refresh decision (registry status, risk level, AML hits).
- **ACTIVATION**: set `DIDIT_API_KEY` + `DIDIT_WORKFLOW_ID` (KYB workflow UUID) in backend/.env. Currently EMPTY → runs in "belum dikonfigurasi" mode. Use sandbox key (free) or live (500 checks/month free).
- Bug fixes: bank name-check SIMULASI mismatch now works; NIB QR domain hardened (urlparse hostname == oss.go.id). Tested: iteration_4.json 15/15 pass.

## PDF Report + Didit Webhook Auto-Sync (2026-08-01)
- **PDF export**: `GET /api/applications/{id}/report.pdf` (reportlab) — full risk report: profil perusahaan, breakdown skor kredit, validasi NIB+bank, screening hits, hasil Didit, keputusan. Frontend button "Ekspor PDF" (blob download) di halaman kasus. Ownership-guarded.
- **Didit webhook auto-sync**: `POST /api/didit/webhook` — verifies X-Signature-V2/Simple HMAC (when DIDIT_WEBHOOK_SECRET set) + 300s window; `vendor_data` = application id; status Approved → auto-approve, Declined → auto-reject (decided_by "SYSTEM (Didit)"), guarded against overriding finalized apps.
- Tested: iteration_5.json 27/27 pass (12 new + 15 regression).

## Didit Activation Instructions (pending user keys)
1. Console business.didit.me → API Keys → copy API key (Sandbox = free / Live = 500 checks/month free).
2. Console → Workflows → create a KYB workflow → copy workflow_id (UUID).
3. Console → API & Webhooks → Add destination, URL = `{REACT_APP_BACKEND_URL}/api/didit/webhook`, subscribe `status.updated`, copy secret_shared_key.
4. Set in backend/.env: DIDIT_API_KEY, DIDIT_WORKFLOW_ID, DIDIT_WEBHOOK_SECRET → `sudo supervisorctl restart backend`.

## Audit Trail + Per-UBO KYC + Branded PDF (2026-08-01)
- **Audit trail webhook**: append-only `db.didit_events` records EVERY inbound Didit webhook (event_id, app_id, vendor_data, status, verified flag, received_at); `GET /api/applications/{id}/didit/events`. Shown as "Audit Trail Webhook" list in the Didit card.
- **Per-UBO Didit KYC**: `POST /api/applications/{id}/directors/{index}/didit-session` (vendor_data `{id}:dir:{index}`, uses DIDIT_KYC_WORKFLOW_ID). Webhook branch updates `application.director_kyc[idx].status` without changing the app decision. Frontend: per-director "Verifikasi KYC" button + status badge.
- **Branded PDF**: report.pdf now has a dark CorpScore letterhead (kop) with wordmark + accent + "RAHASIA/CONFIDENTIAL" and footer with page number.
- Tested: iteration_6.json 47/47 pass (20 new + 27 regression). Visually verified PDF letterhead.
- New env: DIDIT_KYC_WORKFLOW_ID (optional; falls back to DIDIT_WORKFLOW_ID for person KYC).
