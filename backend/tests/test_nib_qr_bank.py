"""New feature tests: NIB QR verify + BRIAPI bank name-check (SIMULASI) + submit integration."""
import io
import os
import uuid
import pytest
import requests
import qrcode

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://corpscore-kyb.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

OWNER_EMAIL = "rizkyjo@pegasusexchange.id"
OWNER_PW = "Pegasus2026!"


def _client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _qr_png_bytes(text: str) -> bytes:
    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def owner():
    s = _client()
    r = s.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PW})
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def applicant():
    s = _client()
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "Test User"})
    assert r.status_code == 200
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def applicant2():
    s = _client()
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "Other User"})
    assert r.status_code == 200
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


def _payload(nib="9120001112223", expiry="2030-12-31", legal=None, holder=None):
    legal = legal or f"TEST_PT Nusantara {uuid.uuid4().hex[:6]}"
    return {
        "legal_name": legal, "brand_name": "Nusantara", "entity_type": "PT",
        "nib": nib, "nib_expiry_date": expiry, "npwp": "01.234.567.8-901.000",
        "deed_number": "AHU-123", "established_year": 2020, "industry": "fintech",
        "address": "Jl. Sudirman No.1", "annual_revenue_idr": 3_000_000_000, "paid_up_capital_idr": 1_000_000_000,
        "bank_name": "Bank Central Asia", "bank_code": "014",
        "bank_account_number": "1234567890",
        "bank_account_holder": holder or legal,
        "directors": [{"name": "John Doe", "role": "CEO", "is_pep": False, "ownership_pct": 100}],
    }


def _create(client, **kw):
    r = client.post(f"{API}/applications", json=_payload(**kw))
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ------------- NIB QR verify -------------
class TestVerifyNibQR:
    def test_qr_matches_input_and_simulasi_registry(self, applicant):
        nib = "9120001112223"
        aid = _create(applicant, nib=nib)
        qr_bytes = _qr_png_bytes(f"https://oss.go.id/informasi/detail-nib/{nib}")
        files = {"file": ("nib.png", qr_bytes, "image/png")}
        # requests session has Content-Type json; override by not sending headers for multipart
        h = {k: v for k, v in applicant.headers.items() if k.lower() != "content-type"}
        r = requests.post(f"{API}/applications/{aid}/verify-nib", files=files, headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["nib"]["format_valid"] == True
        qr = d["nib"]["qr"]
        assert qr["success"] == True
        assert qr["domain_valid"] == True
        assert qr["nib_in_qr"] == nib
        assert qr["matches_input"] == True
        reg = d["nib"]["registry"]
        assert reg["source"] == "SIMULASI"
        assert reg["status"] == "AKTIF"
        assert d["nib"]["valid"] == True

    def test_qr_mismatch_marks_invalid(self, applicant):
        aid = _create(applicant, nib="9120001112223")
        # QR encodes different NIB
        qr_bytes = _qr_png_bytes("https://oss.go.id/informasi/detail-nib/1111111111111")
        files = {"file": ("nib.png", qr_bytes, "image/png")}
        h = {k: v for k, v in applicant.headers.items() if k.lower() != "content-type"}
        r = requests.post(f"{API}/applications/{aid}/verify-nib", files=files, headers=h)
        assert r.status_code == 200
        d = r.json()
        assert d["nib"]["qr"]["matches_input"] == False
        assert d["nib"]["valid"] == False
        assert "qr" in (d["nib"]["reason"] or "").lower() or "cocok" in (d["nib"]["reason"] or "").lower()

    def test_qr_mismatch_submit_auto_rejected(self, applicant):
        aid = _create(applicant, nib="9120001112223")
        qr_bytes = _qr_png_bytes("https://oss.go.id/informasi/detail-nib/1111111111111")
        files = {"file": ("nib.png", qr_bytes, "image/png")}
        h = {k: v for k, v in applicant.headers.items() if k.lower() != "content-type"}
        r = requests.post(f"{API}/applications/{aid}/verify-nib", files=files, headers=h)
        assert r.status_code == 200
        r2 = applicant.post(f"{API}/applications/{aid}/submit")
        assert r2.status_code == 200, r2.text
        d = r2.json()
        assert d["status"] == "auto_rejected"
        reason = (d.get("auto_reject_reason") or "").lower()
        assert "qr" in reason or "cocok" in reason

    def test_non_oss_domain_invalid(self, applicant):
        aid = _create(applicant, nib="9120001112223")
        qr_bytes = _qr_png_bytes("https://evil.example.com/nib/9120001112223")
        files = {"file": ("nib.png", qr_bytes, "image/png")}
        h = {k: v for k, v in applicant.headers.items() if k.lower() != "content-type"}
        r = requests.post(f"{API}/applications/{aid}/verify-nib", files=files, headers=h)
        assert r.status_code == 200
        qr = r.json()["nib"]["qr"]
        assert qr["success"] == True
        assert qr["domain_valid"] == False
        assert qr["nib_in_qr"] == "9120001112223"
        assert qr["matches_input"] == True  # NIB itself matches; only domain flag differs

    def test_format_invalid_nib(self, applicant):
        aid = _create(applicant, nib="123")
        # No file uploaded
        h = {k: v for k, v in applicant.headers.items() if k.lower() != "content-type"}
        r = requests.post(f"{API}/applications/{aid}/verify-nib", headers=h)
        assert r.status_code == 200
        d = r.json()
        assert d["nib"]["format_valid"] == False
        assert d["nib"]["valid"] == False

    def test_verify_nib_requires_auth(self, applicant):
        aid = _create(applicant)
        r = requests.post(f"{API}/applications/{aid}/verify-nib")
        assert r.status_code == 401

    def test_verify_nib_rbac_other_applicant(self, applicant, applicant2):
        aid = _create(applicant)
        h = {k: v for k, v in applicant2.headers.items() if k.lower() != "content-type"}
        r = requests.post(f"{API}/applications/{aid}/verify-nib", headers=h)
        assert r.status_code == 403


# ------------- Bank verify -------------
class TestVerifyBank:
    def test_bank_verify_simulasi_matches(self, applicant):
        legal = f"TEST_PT Verif {uuid.uuid4().hex[:6]}"
        aid = _create(applicant, legal=legal, holder=legal)
        r = applicant.post(f"{API}/applications/{aid}/verify-bank")
        assert r.status_code == 200, r.text
        b = r.json()["bank"]
        assert b["source"] == "SIMULASI"
        assert b["verified"] == True
        assert b["status"] == "verified"
        assert b["resolved_name"] == legal
        assert b["name_match_score"] >= 50
        assert b["account_number_masked"].startswith("••••")

    def test_bank_verify_simulasi_mismatch(self, applicant):
        aid = _create(applicant, holder="Totally Unrelated Name Zzz")
        r = applicant.post(f"{API}/applications/{aid}/verify-bank")
        assert r.status_code == 200
        b = r.json()["bank"]
        assert b["verified"] == False
        assert b["status"] == "mismatch"
        assert b["name_match_score"] < 50

    def test_verify_bank_requires_auth(self, applicant):
        aid = _create(applicant)
        r = requests.post(f"{API}/applications/{aid}/verify-bank")
        assert r.status_code == 401

    def test_verify_bank_rbac_other_applicant(self, applicant, applicant2):
        aid = _create(applicant)
        r = applicant2.post(f"{API}/applications/{aid}/verify-bank")
        assert r.status_code == 403


# ------------- Submit integration -------------
class TestSubmitIntegration:
    def test_valid_full_flow_under_review(self, owner, applicant):
        nib = "9120001112223"
        legal = f"TEST_PT Full {uuid.uuid4().hex[:6]}"
        aid = _create(applicant, nib=nib, legal=legal, holder=legal)
        # attach matching QR
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
        assert d["sla_due_at"]
        # persisted qr + registry survive via GET (owner)
        r3 = owner.get(f"{API}/applications/{aid}")
        v = r3.json()["validation"]
        assert v["nib"]["qr"]["domain_valid"] == True
        assert v["nib"]["qr"]["matches_input"] == True
        assert v["nib"]["registry"]["source"] == "SIMULASI"
        assert v["bank"]["source"] == "SIMULASI"
        assert v["bank"]["verified"] == True

    def test_finalised_cannot_resubmit(self, applicant):
        # expired -> auto_rejected then re-submit blocked (per code review from iter2)
        aid = _create(applicant, expiry="2020-01-01")
        r1 = applicant.post(f"{API}/applications/{aid}/submit")
        assert r1.status_code == 200
        assert r1.json()["status"] == "auto_rejected"
        r2 = applicant.post(f"{API}/applications/{aid}/submit")
        # Backend now blocks resubmission of finalised apps
        assert r2.status_code == 400
