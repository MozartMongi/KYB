"""Iteration 6 tests: Audit trail webhook events + Per-UBO Didit KYC + Branded PDF.
Extends coverage on:
 - GET /api/applications/{id}/didit/events (auth/ownership, newest-first)
 - POST /api/applications/{id}/directors/{index}/didit-session (unconfigured, 404 idx, RBAC)
 - Per-UBO webhook branch updates director_kyc, not app status
 - App-level webhook still works + guard
 - Branded PDF (still returns %PDF, > several KB now for branded)
"""
import io
import os
import uuid
import time
import pytest
import requests
import qrcode

def _read_env(path, key):
    try:
        with open(path) as f:
            for line in f:
                if line.startswith(key + '='):
                    return line.split('=', 1)[1].strip()
    except Exception:
        return ''
    return ''

BASE_URL = (os.environ.get('REACT_APP_BACKEND_URL') or _read_env('/app/frontend/.env', 'REACT_APP_BACKEND_URL')).rstrip('/')
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
API = f"{BASE_URL}/api"

OWNER_EMAIL = "rizkyjo@pegasusexchange.id"
OWNER_PW = "Pegasus2026!"


def _client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _qr_png_bytes(text: str) -> bytes:
    q = qrcode.QRCode(box_size=10, border=4)
    q.add_data(text); q.make(fit=True)
    img = q.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()


def _payload(nib="9120001112223", expiry="2030-12-31", legal=None, holder=None, directors=None):
    legal = legal or f"TEST_PT It6 {uuid.uuid4().hex[:6]}"
    return {
        "legal_name": legal, "brand_name": "It6", "entity_type": "PT",
        "nib": nib, "nib_expiry_date": expiry, "npwp": "01.234.567.8-901.000",
        "deed_number": "AHU-123", "established_year": 2020, "industry": "fintech",
        "address": "Jl. Sudirman No.1", "annual_revenue_idr": 3_000_000_000, "paid_up_capital_idr": 1_000_000_000,
        "bank_name": "Bank Central Asia", "bank_code": "014",
        "bank_account_number": "1234567890",
        "bank_account_holder": holder or legal,
        "directors": directors or [
            {"name": "Alice CEO", "role": "CEO", "is_pep": False, "ownership_pct": 60},
            {"name": "Bob COO", "role": "COO", "is_pep": False, "ownership_pct": 40},
        ],
    }


@pytest.fixture(scope="module")
def applicant():
    s = _client()
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "It6 User"})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def applicant2():
    s = _client()
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "It6 Other"})
    assert r.status_code == 200
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def owner():
    s = _client()
    r = s.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PW})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


def _create(client, **kw):
    r = client.post(f"{API}/applications", json=_payload(**kw))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _submit_under_review(applicant, aid, nib="9120001112223"):
    qr_bytes = _qr_png_bytes(f"https://oss.go.id/informasi/detail-nib/{nib}")
    h = {k: v for k, v in applicant.headers.items() if k.lower() != "content-type"}
    requests.post(f"{API}/applications/{aid}/verify-nib",
                  files={"file": ("nib.png", qr_bytes, "image/png")}, headers=h)
    r = applicant.post(f"{API}/applications/{aid}/submit")
    assert r.status_code == 200, r.text


# ============ Per-UBO Didit session endpoint ============
class TestPerUboSession:
    def test_unconfigured_returns_configured_false(self, applicant):
        aid = _create(applicant)
        r = applicant.post(f"{API}/applications/{aid}/directors/0/didit-session")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("configured") == False or j.get("demo") == True, j

    def test_index_out_of_range_404(self, applicant):
        aid = _create(applicant)
        r = applicant.post(f"{API}/applications/{aid}/directors/9/didit-session")
        assert r.status_code == 404, r.text

    def test_negative_index_404(self, applicant):
        aid = _create(applicant)
        # FastAPI will coerce; -1 goes through path but our code checks < 0
        r = applicant.post(f"{API}/applications/{aid}/directors/-1/didit-session")
        assert r.status_code in (404, 422), r.status_code

    def test_requires_auth(self, applicant):
        aid = _create(applicant)
        r = requests.post(f"{API}/applications/{aid}/directors/0/didit-session")
        assert r.status_code == 401

    def test_rbac_other_applicant_forbidden(self, applicant, applicant2):
        aid = _create(applicant)
        r = applicant2.post(f"{API}/applications/{aid}/directors/0/didit-session")
        assert r.status_code == 403

    def test_owner_can_call(self, owner, applicant):
        aid = _create(applicant)
        r = owner.post(f"{API}/applications/{aid}/directors/0/didit-session")
        assert r.status_code == 200
        j = r.json()
        assert j.get("configured") == False or j.get("demo") == True, j

    def test_missing_application_404(self, applicant):
        r = applicant.post(f"{API}/applications/nonexistent_xyz/directors/0/didit-session")
        assert r.status_code == 404


# ============ Audit trail events endpoint ============
class TestDiditEvents:
    def test_events_newest_first_and_fields(self, applicant, owner):
        aid = _create(applicant)
        _submit_under_review(applicant, aid)
        # Fire app-level event
        wh_app = {
            "webhook_type": "status.updated", "status": "Approved", "vendor_data": aid,
            "session_id": "sess_A", "event_id": f"evt_A_{uuid.uuid4().hex[:6]}",
        }
        r1 = requests.post(f"{API}/didit/webhook", json=wh_app); assert r1.status_code == 200
        time.sleep(0.05)
        # Fire per-UBO event
        wh_ubo = {
            "webhook_type": "status.updated", "status": "Approved", "vendor_data": f"{aid}:dir:0",
            "session_id": "sess_B", "event_id": f"evt_B_{uuid.uuid4().hex[:6]}",
        }
        r2 = requests.post(f"{API}/didit/webhook", json=wh_ubo); assert r2.status_code == 200

        r = owner.get(f"{API}/applications/{aid}/didit/events")
        assert r.status_code == 200, r.text
        evs = r.json()
        assert isinstance(evs, list)
        assert len(evs) >= 2, evs
        # required fields
        for e in evs[:2]:
            assert "webhook_type" in e and "status" in e and "vendor_data" in e and "verified" in e
        # newest first: received_at should be non-increasing
        rec = [e.get("received_at") for e in evs]
        assert rec == sorted(rec, reverse=True), rec
        # verified True because DIDIT_WEBHOOK_SECRET is empty
        assert evs[0]["verified"] == True

    def test_events_requires_auth(self, applicant):
        aid = _create(applicant)
        r = requests.get(f"{API}/applications/{aid}/didit/events")
        assert r.status_code == 401

    def test_events_rbac(self, applicant, applicant2):
        aid = _create(applicant)
        r = applicant2.get(f"{API}/applications/{aid}/didit/events")
        assert r.status_code == 403

    def test_events_404_missing_app(self, owner):
        r = owner.get(f"{API}/applications/nope_xxx/didit/events")
        assert r.status_code == 404


# ============ Per-UBO webhook branch ============
class TestPerUboWebhook:
    def test_ubo_webhook_updates_director_kyc_only(self, applicant, owner):
        aid = _create(applicant)
        _submit_under_review(applicant, aid)
        before = owner.get(f"{API}/applications/{aid}").json()
        assert before["status"] == "under_review"

        wh = {
            "webhook_type": "status.updated", "status": "Approved", "vendor_data": f"{aid}:dir:0",
            "session_id": "sess_ubo_0", "event_id": f"evt_ubo_{uuid.uuid4().hex[:6]}",
        }
        r = requests.post(f"{API}/didit/webhook", json=wh)
        assert r.status_code == 200

        after = owner.get(f"{API}/applications/{aid}").json()
        assert after["status"] == "under_review", after  # app status UNCHANGED
        assert after.get("decided_by") != "SYSTEM (Didit)"
        dk = after.get("director_kyc") or {}
        assert dk.get("0", {}).get("status") == "Approved", dk

    def test_ubo_declined_only_updates_director(self, applicant, owner):
        aid = _create(applicant)
        _submit_under_review(applicant, aid)
        wh = {
            "webhook_type": "status.updated", "status": "Declined", "vendor_data": f"{aid}:dir:1",
            "session_id": "sess_ubo_1", "event_id": f"evt_ubo_{uuid.uuid4().hex[:6]}",
        }
        r = requests.post(f"{API}/didit/webhook", json=wh)
        assert r.status_code == 200

        a = owner.get(f"{API}/applications/{aid}").json()
        assert a["status"] == "under_review"
        assert (a.get("director_kyc") or {}).get("1", {}).get("status") == "Declined"


# ============ App-level webhook regression ============
class TestAppLevelWebhookRegression:
    def test_app_level_approved(self, applicant, owner):
        aid = _create(applicant)
        _submit_under_review(applicant, aid)
        wh = {"webhook_type": "status.updated", "status": "Approved",
              "vendor_data": aid, "session_id": "sess_x", "event_id": f"evt_{uuid.uuid4().hex[:6]}"}
        r = requests.post(f"{API}/didit/webhook", json=wh)
        assert r.status_code == 200
        a = owner.get(f"{API}/applications/{aid}").json()
        assert a["status"] == "approved"
        assert a.get("decided_by") == "SYSTEM (Didit)"

    def test_app_level_declined(self, applicant, owner):
        aid = _create(applicant)
        _submit_under_review(applicant, aid)
        wh = {"webhook_type": "status.updated", "status": "Declined",
              "vendor_data": aid, "session_id": "sess_x", "event_id": f"evt_{uuid.uuid4().hex[:6]}"}
        r = requests.post(f"{API}/didit/webhook", json=wh)
        assert r.status_code == 200
        a = owner.get(f"{API}/applications/{aid}").json()
        assert a["status"] == "rejected"
        assert a.get("decided_by") == "SYSTEM (Didit)"

    def test_guard_no_override_after_manual(self, applicant, owner):
        aid = _create(applicant)
        _submit_under_review(applicant, aid)
        ra = owner.post(f"{API}/applications/{aid}/decision", json={"decision": "approved", "notes": "manual"})
        assert ra.status_code == 200
        wh = {"webhook_type": "status.updated", "status": "Declined",
              "vendor_data": aid, "session_id": "sess_x", "event_id": f"evt_{uuid.uuid4().hex[:6]}"}
        requests.post(f"{API}/didit/webhook", json=wh)
        a = owner.get(f"{API}/applications/{aid}").json()
        assert a["status"] == "approved"
        assert a.get("decided_by") != "SYSTEM (Didit)"


# ============ Branded PDF ============
class TestBrandedPdf:
    def test_pdf_content_and_size(self, applicant):
        aid = _create(applicant)
        r = applicant.get(f"{API}/applications/{aid}/report.pdf")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"
        # Branded PDF should be larger than baseline (letterhead+footer)
        assert len(r.content) > 1500, len(r.content)

    def test_pdf_404_missing(self, owner):
        r = owner.get(f"{API}/applications/no_such_app/report.pdf")
        assert r.status_code == 404

    def test_pdf_forbidden_other(self, applicant, applicant2):
        aid = _create(applicant)
        r = applicant2.get(f"{API}/applications/{aid}/report.pdf")
        assert r.status_code == 403

    def test_pdf_requires_auth(self, applicant):
        aid = _create(applicant)
        r = requests.get(f"{API}/applications/{aid}/report.pdf")
        assert r.status_code == 401
