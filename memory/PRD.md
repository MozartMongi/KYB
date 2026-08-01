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
- ✅ Tested: backend 15/16 (1 test-infra artifact), frontend 100% of critical flows.

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
