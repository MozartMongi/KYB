"""Iteration 4 tests:
 - Bank name-check SIMULASI: mismatch path (holder unrelated -> verified=false)
 - Bank name-check SIMULASI: match path (holder == legal -> verified=true)
 - NIB QR domain hardening (hostname suffix, not substring)
 - Didit endpoints unconfigured path + RBAC + decision 400
"""
import io
import os
import uuid
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
    q = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    q.add_data(text)
    q.make(fit=True)
    img = q.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _payload(nib="9120001112223", expiry="2030-12-31", legal=None, holder=None):
    legal = legal or f"TEST_PT ABC Sejahtera {uuid.uuid4().hex[:6]}"
    return {
        "legal_name": legal, "brand_name": "ABC", "entity_type": "PT",
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
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "It4 User"})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def applicant2():
    s = _client()
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "It4 Other"})
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


# ---------- REGRESSION FIX: bank mismatch ----------
class TestBankMismatchFix:
    def test_bank_mismatch_when_holder_unrelated(self, applicant):
        aid = _create(applicant,
                      legal="PT ABC Sejahtera",
                      holder="Orang Tidak Berhubungan Zzz")
        r = applicant.post(f"{API}/applications/{aid}/verify-bank")
        assert r.status_code == 200, r.text
        b = r.json()["bank"]
        assert b["source"] == "SIMULASI"
        assert b["verified"] is False, b
        assert b["status"] == "mismatch", b
        assert b["name_match_score"] < 50, b

    def test_bank_match_when_holder_equals_legal(self, applicant):
        legal = f"TEST_PT ABC {uuid.uuid4().hex[:6]}"
        aid = _create(applicant, legal=legal, holder=legal)
        r = applicant.post(f"{API}/applications/{aid}/verify-bank")
        assert r.status_code == 200
        b = r.json()["bank"]
        assert b["verified"] is True
        assert b["status"] == "verified"


# ---------- NIB QR domain hardening ----------
class TestQrDomainHardening:
    def test_malicious_lookalike_domain_invalid(self, applicant):
        aid = _create(applicant, nib="9120001112223")
        qr_bytes = _qr_png_bytes("https://oss.go.id.malicious.example/x/9120001112223")
        h = {k: v for k, v in applicant.headers.items() if k.lower() != "content-type"}
        r = requests.post(f"{API}/applications/{aid}/verify-nib",
                          files={"file": ("nib.png", qr_bytes, "image/png")}, headers=h)
        assert r.status_code == 200, r.text
        qr = r.json()["nib"]["qr"]
        assert qr["success"] is True
        assert qr["domain_valid"] is False, qr

    def test_real_oss_domain_valid(self, applicant):
        aid = _create(applicant, nib="9120001112223")
        qr_bytes = _qr_png_bytes("https://oss.go.id/informasi/detail-nib/9120001112223")
        h = {k: v for k, v in applicant.headers.items() if k.lower() != "content-type"}
        r = requests.post(f"{API}/applications/{aid}/verify-nib",
                          files={"file": ("nib.png", qr_bytes, "image/png")}, headers=h)
        assert r.status_code == 200
        qr = r.json()["nib"]["qr"]
        assert qr["domain_valid"] is True, qr

    def test_subdomain_oss_valid(self, applicant):
        aid = _create(applicant, nib="9120001112223")
        qr_bytes = _qr_png_bytes("https://api.oss.go.id/detail/9120001112223")
        h = {k: v for k, v in applicant.headers.items() if k.lower() != "content-type"}
        r = requests.post(f"{API}/applications/{aid}/verify-nib",
                          files={"file": ("nib.png", qr_bytes, "image/png")}, headers=h)
        assert r.status_code == 200
        qr = r.json()["nib"]["qr"]
        if not qr.get("success"):
            pytest.skip(f"opencv couldn't decode subdomain QR on server: {qr}")
        assert qr["domain_valid"] is True, qr


# ---------- Didit unconfigured + RBAC ----------
class TestDidit:
    def test_didit_session_unconfigured(self, applicant):
        aid = _create(applicant)
        r = applicant.post(f"{API}/applications/{aid}/didit/session")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("configured") is False, d

    def test_didit_decision_requires_session(self, applicant):
        aid = _create(applicant)
        r = applicant.get(f"{API}/applications/{aid}/didit/decision")
        assert r.status_code == 400, r.text

    def test_didit_session_requires_auth(self, applicant):
        aid = _create(applicant)
        r = requests.post(f"{API}/applications/{aid}/didit/session")
        assert r.status_code == 401

    def test_didit_decision_requires_auth(self, applicant):
        aid = _create(applicant)
        r = requests.get(f"{API}/applications/{aid}/didit/decision")
        assert r.status_code == 401

    def test_didit_session_rbac_other_applicant(self, applicant, applicant2):
        aid = _create(applicant)
        r = applicant2.post(f"{API}/applications/{aid}/didit/session")
        assert r.status_code == 403

    def test_didit_decision_rbac_other_applicant(self, applicant, applicant2):
        aid = _create(applicant)
        r = applicant2.get(f"{API}/applications/{aid}/didit/decision")
        assert r.status_code == 403

    def test_didit_owner_can_access(self, owner, applicant):
        aid = _create(applicant)
        r = owner.post(f"{API}/applications/{aid}/didit/session")
        assert r.status_code == 200
        assert r.json().get("configured") is False


# ---------- Regression full onboarding ----------
class TestFullOnboardingRegression:
    def test_valid_flow_under_review(self, owner, applicant):
        nib = "9120001112223"
        legal = f"TEST_PT Reg {uuid.uuid4().hex[:6]}"
        aid = _create(applicant, nib=nib, legal=legal, holder=legal)
        qr_bytes = _qr_png_bytes(f"https://oss.go.id/informasi/detail-nib/{nib}")
        h = {k: v for k, v in applicant.headers.items() if k.lower() != "content-type"}
        r = requests.post(f"{API}/applications/{aid}/verify-nib",
                          files={"file": ("nib.png", qr_bytes, "image/png")}, headers=h)
        assert r.status_code == 200
        r2 = applicant.post(f"{API}/applications/{aid}/submit")
        assert r2.status_code == 200, r2.text
        d = r2.json()
        assert d["status"] == "under_review"
        assert d["sla_days"] == 3
        # owner GET
        r3 = owner.get(f"{API}/applications/{aid}")
        assert r3.status_code == 200
        body = r3.json()
        v = body["validation"]
        assert v["nib"]["qr"]["domain_valid"] is True
        assert v["nib"]["registry"]["source"] == "SIMULASI"
        assert v["bank"]["verified"] is True

    def test_expired_nib_auto_rejected(self, applicant):
        aid = _create(applicant, expiry="2020-01-01")
        r = applicant.post(f"{API}/applications/{aid}/submit")
        assert r.status_code == 200
        assert r.json()["status"] == "auto_rejected"

    def test_owner_approve_flow(self, owner, applicant):
        nib = "9120001112223"
        legal = f"TEST_PT Approve {uuid.uuid4().hex[:6]}"
        aid = _create(applicant, nib=nib, legal=legal, holder=legal)
        qr_bytes = _qr_png_bytes(f"https://oss.go.id/informasi/detail-nib/{nib}")
        h = {k: v for k, v in applicant.headers.items() if k.lower() != "content-type"}
        requests.post(f"{API}/applications/{aid}/verify-nib",
                      files={"file": ("nib.png", qr_bytes, "image/png")}, headers=h)
        rs = applicant.post(f"{API}/applications/{aid}/submit")
        assert rs.status_code == 200
        ra = owner.post(f"{API}/applications/{aid}/decision",
                        json={"decision": "approved", "notes": "Looks good"})
        assert ra.status_code == 200, ra.text
        assert ra.json()["status"] == "approved"
