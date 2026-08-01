"""KYB Backend API tests - covers auth, applications CRUD, screening, scoring, decisions, RBAC."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://corpscore-kyb.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

OWNER_EMAIL = "rizkyjo@pegasusexchange.id"
OWNER_PW = "Pegasus2026!"


def _client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def owner():
    s = _client()
    r = s.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PW})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["role"] == "owner"
    s.headers.update({"Authorization": f"Bearer {data['token']}"})
    return s


@pytest.fixture(scope="module")
def applicant():
    s = _client()
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "Test Applicant"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["role"] == "applicant"
    s.headers.update({"Authorization": f"Bearer {data['token']}"})
    s.applicant_email = email
    s.applicant_user_id = data["user_id"]
    return s


# ---- Auth ----
class TestAuth:
    def test_owner_login(self, owner):
        r = owner.get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json()["email"] == OWNER_EMAIL
        assert r.json()["role"] == "owner"

    def test_login_bad_pw(self):
        r = requests.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": "wrong"})
        assert r.status_code == 401

    def test_register_duplicate(self, applicant):
        r = requests.post(f"{API}/auth/register", json={"email": applicant.applicant_email, "password": "x", "name": "x"})
        assert r.status_code == 400

    def test_me_unauth(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401


# ---- Application CRUD + submit ----
class TestApplication:
    def test_create_and_get(self, applicant):
        payload = {
            "legal_name": f"TEST_PT Nusantara {uuid.uuid4().hex[:6]}",
            "entity_type": "PT", "nib": "1234567890123", "npwp": "01.234.567.8-901.000",
            "deed_number": "AHU-123", "established_year": 2020, "industry": "fintech",
            "address": "Jl. Sudirman No.1", "annual_revenue_idr": 3_000_000_000,
            "paid_up_capital_idr": 1_000_000_000,
            "directors": [{"name": "John Doe", "role": "CEO", "is_pep": False, "ownership_pct": 60}],
        }
        r = applicant.post(f"{API}/applications", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "draft"
        assert d["company"]["legal_name"] == payload["legal_name"]
        assert d["applicant_email"] == applicant.applicant_email
        app_id = d["id"]

        r2 = applicant.get(f"{API}/applications/{app_id}")
        assert r2.status_code == 200
        assert r2.json()["id"] == app_id
        applicant.app_id = app_id

    def test_list_only_own(self, applicant):
        r = applicant.get(f"{API}/applications")
        assert r.status_code == 200
        apps = r.json()
        for a in apps:
            assert a["applicant_user_id"] == applicant.applicant_user_id

    def test_owner_sees_all(self, owner, applicant):
        r = owner.get(f"{API}/applications")
        assert r.status_code == 200
        ids = [a["id"] for a in r.json()]
        assert applicant.app_id in ids

    def test_submit_low_risk(self, applicant):
        r = applicant.post(f"{API}/applications/{applicant.app_id}/submit")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "under_review"
        assert d["score"]["final_score"] > 0
        assert d["score"]["risk_level"] in ("LOW", "MEDIUM", "HIGH")
        assert "legality" in d["score"] and "financial" in d["score"]
        # John Doe should not be on watchlist
        assert d["screening_hits"] == [] or all(h["type"] != "SANCTION" for h in d["screening_hits"])

    def test_screening_sanction_hit(self, applicant):
        payload = {
            "legal_name": f"TEST_PT Sanction {uuid.uuid4().hex[:6]}",
            "entity_type": "PT", "nib": "999", "npwp": "999", "industry": "crypto_exchange",
            "directors": [
                {"name": "Ali Rahman", "role": "Director", "is_pep": False},
                {"name": "Budi Hartono Santoso", "role": "Commissioner", "is_pep": True},
            ],
        }
        r = applicant.post(f"{API}/applications", json=payload)
        assert r.status_code == 200
        aid = r.json()["id"]
        r2 = applicant.post(f"{API}/applications/{aid}/submit")
        assert r2.status_code == 200
        d = r2.json()
        hits = d["screening_hits"]
        assert len(hits) >= 2
        types = {h["type"] for h in hits}
        assert "SANCTION" in types
        assert "PEP" in types
        assert d["score"]["risk_level"] == "HIGH"
        applicant.hit_app_id = aid

    def test_rbac_forbidden(self, applicant):
        other = _client()
        email = f"other_{uuid.uuid4().hex[:8]}@example.com"
        rr = other.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "Other"})
        assert rr.status_code == 200
        other.headers.update({"Authorization": f"Bearer {rr.json()['token']}"})
        r = other.get(f"{API}/applications/{applicant.app_id}")
        assert r.status_code == 403

    def test_decision_requires_officer(self, applicant):
        r = applicant.post(f"{API}/applications/{applicant.app_id}/decision",
                           json={"decision": "approved", "note": "ok"})
        assert r.status_code == 403

    def test_owner_approves(self, owner, applicant):
        r = owner.post(f"{API}/applications/{applicant.app_id}/decision",
                       json={"decision": "approved", "note": "Looks good"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "approved"
        assert d["decision"] == "approved"
        assert d["decision_note"] == "Looks good"
        assert d["decided_by"] == OWNER_EMAIL

    def test_owner_rejects(self, owner, applicant):
        r = owner.post(f"{API}/applications/{applicant.hit_app_id}/decision",
                       json={"decision": "rejected", "note": "Sanction hit"})
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

    def test_invalid_decision(self, owner, applicant):
        r = owner.post(f"{API}/applications/{applicant.app_id}/decision",
                       json={"decision": "maybe", "note": ""})
        assert r.status_code == 400


class TestDashboard:
    def test_stats_owner(self, owner):
        r = owner.get(f"{API}/dashboard/stats")
        assert r.status_code == 200
        d = r.json()
        for k in ("total", "by_status", "risk_counts", "pending_review", "avg_score"):
            assert k in d
        assert d["total"] >= 2

    def test_stats_applicant_scope(self, applicant):
        r = applicant.get(f"{API}/dashboard/stats")
        assert r.status_code == 200
        assert r.json()["total"] >= 2
