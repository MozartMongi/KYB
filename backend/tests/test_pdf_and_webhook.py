"""Iteration 5 tests: PDF export + Didit webhook auto-sync + guards."""
import io
import os
import uuid
import json
import pytest
import requests
import qrcode

BASE_URL = (os.environ.get('REACT_APP_BACKEND_URL') or 'https://corpscore-kyb.preview.emergentagent.com').rstrip('/')
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


def _payload(nib="9120001112223", expiry="2030-12-31", legal=None, holder=None):
    legal = legal or f"TEST_PT PDF {uuid.uuid4().hex[:6]}"
    return {
        "legal_name": legal, "brand_name": "PDF", "entity_type": "PT",
        "nib": nib, "nib_expiry_date": expiry, "npwp": "01.234.567.8-901.000",
        "deed_number": "AHU-123", "established_year": 2020, "industry": "fintech",
        "address": "Jl. Sudirman No.1", "annual_revenue_idr": 3_000_000_000, "paid_up_capital_idr": 1_000_000_000,
        "bank_name": "Bank Central Asia", "bank_code": "014",
        "bank_account_number": "1234567890",
        "bank_account_holder": holder or legal,
        "directors": [{"name": "John Doe", "role": "CEO", "is_pep": False, "ownership_pct": 100}],
    }


@pytest.fixture(scope="module")
def applicant():
    s = _client()
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "It5 User"})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def applicant2():
    s = _client()
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "It5 Other"})
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
    assert r.json()["status"] == "under_review", r.text


# ================ PDF Export ================
class TestPdfExport:
    def test_pdf_export_by_applicant(self, applicant):
        aid = _create(applicant)
        r = applicant.get(f"{API}/applications/{aid}/report.pdf")
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/pdf"), r.headers
        assert r.content[:4] == b"%PDF", r.content[:20]
        assert len(r.content) > 500

    def test_pdf_export_requires_auth(self, applicant):
        aid = _create(applicant)
        r = requests.get(f"{API}/applications/{aid}/report.pdf")
        assert r.status_code == 401, r.status_code

    def test_pdf_export_forbidden_other_applicant(self, applicant, applicant2):
        aid = _create(applicant)
        r = applicant2.get(f"{API}/applications/{aid}/report.pdf")
        assert r.status_code == 403, r.status_code

    def test_pdf_export_by_owner(self, owner, applicant):
        aid = _create(applicant)
        r = owner.get(f"{API}/applications/{aid}/report.pdf")
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_pdf_export_404(self, owner):
        r = owner.get(f"{API}/applications/doesnotexist_xyz/report.pdf")
        assert r.status_code == 404


# ================ Webhook auto-sync ================
class TestDiditWebhook:
    def _wh(self, app_id, status, wh_type="status.updated"):
        return {
            "webhook_type": wh_type, "status": status, "vendor_data": app_id,
            "session_id": f"sess_{uuid.uuid4().hex[:8]}", "event_id": f"evt_{uuid.uuid4().hex[:8]}",
            "timestamp": 1700000000, "session_kind": "kyb",
        }

    def test_webhook_approved(self, owner, applicant):
        aid = _create(applicant)
        _submit_under_review(applicant, aid)
        r = requests.post(f"{API}/didit/webhook", json=self._wh(aid, "Approved"))
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}
        # verify
        a = owner.get(f"{API}/applications/{aid}").json()
        assert a["status"] == "approved", a
        assert a.get("decided_by") == "SYSTEM (Didit)", a
        assert (a.get("didit") or {}).get("status") == "Approved", a.get("didit")

    def test_webhook_declined(self, owner, applicant):
        aid = _create(applicant)
        _submit_under_review(applicant, aid)
        r = requests.post(f"{API}/didit/webhook", json=self._wh(aid, "Declined"))
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        a = owner.get(f"{API}/applications/{aid}").json()
        assert a["status"] == "rejected", a
        assert a.get("decided_by") == "SYSTEM (Didit)"
        assert (a.get("didit") or {}).get("status") == "Declined"

    def test_webhook_guard_no_override_already_finalized(self, owner, applicant):
        aid = _create(applicant)
        _submit_under_review(applicant, aid)
        # owner approve first
        ra = owner.post(f"{API}/applications/{aid}/decision",
                        json={"decision": "approved", "notes": "manual approve"})
        assert ra.status_code == 200
        before = owner.get(f"{API}/applications/{aid}").json()
        assert before["status"] == "approved"
        assert before.get("decided_by") != "SYSTEM (Didit)"
        # try to declined via webhook - should NOT override
        r = requests.post(f"{API}/didit/webhook", json=self._wh(aid, "Declined"))
        assert r.status_code == 200
        after = owner.get(f"{API}/applications/{aid}").json()
        assert after["status"] == "approved", after
        assert after.get("decided_by") == before.get("decided_by")

    def test_webhook_non_decision_event(self, owner, applicant):
        aid = _create(applicant)
        _submit_under_review(applicant, aid)
        r = requests.post(f"{API}/didit/webhook",
                          json=self._wh(aid, "Approved", wh_type="session.created"))
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        a = owner.get(f"{API}/applications/{aid}").json()
        assert a["status"] == "under_review", a  # no change

    def test_webhook_unknown_vendor_data(self):
        r = requests.post(f"{API}/didit/webhook", json={
            "webhook_type": "status.updated", "status": "Approved",
            "vendor_data": "does_not_exist_123",
            "session_id": "sess_x", "event_id": "evt_x",
        })
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_webhook_missing_vendor_data(self):
        r = requests.post(f"{API}/didit/webhook", json={
            "webhook_type": "status.updated", "status": "Approved",
            "session_id": "sess_x", "event_id": "evt_x",
        })
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_webhook_secret_empty_accepts_unsigned(self, applicant):
        # No signature headers; secret is empty by design - accepted
        aid = _create(applicant)
        _submit_under_review(applicant, aid)
        r = requests.post(f"{API}/didit/webhook", json=self._wh(aid, "Approved"))
        assert r.status_code == 200, r.text
