from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import json
import base64
import time
import logging
import bcrypt
import jwt
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Form, Header, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("kyb")

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGORITHM = "HS256"
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = "corpscore-kyb"
storage_key = None

app = FastAPI(title="CorpScore KYB")
api_router = APIRouter(prefix="/api")

# ---------------- Storage ----------------
def init_storage():
    global storage_key
    if storage_key:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_LLM_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()

def get_object(path: str):
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

# ---------------- Auth helpers ----------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email, "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "access"}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def set_auth_cookie(response: Response, name: str, value: str):
    response.set_cookie(key=name, value=value, httponly=True, secure=True, samesite="none", max_age=604800, path="/")

async def resolve_user(request: Request):
    # 1. JWT access_token cookie
    token = request.cookies.get("access_token")
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0})
            if user:
                return user
        except jwt.PyJWTError:
            pass
    # 2. session_token cookie or Bearer header (Google auth / JWT bearer)
    stoken = request.cookies.get("session_token")
    if not stoken:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            stoken = auth_header[7:]
    if stoken:
        sess = await db.user_sessions.find_one({"session_token": stoken})
        if sess:
            expires_at = sess["expires_at"]
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at >= datetime.now(timezone.utc):
                user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
                if user:
                    return user
        # maybe it's a JWT passed as bearer
        try:
            payload = jwt.decode(stoken, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0})
            if user:
                return user
        except jwt.PyJWTError:
            pass
    return None

async def get_current_user(request: Request):
    user = await resolve_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user.pop("password_hash", None)
    return user

def require_officer(user: dict):
    if user.get("role") not in ("owner", "officer"):
        raise HTTPException(status_code=403, detail="Compliance officer access required")

# ---------------- Models ----------------
class RegisterInput(BaseModel):
    email: str
    password: str
    name: str

class LoginInput(BaseModel):
    email: str
    password: str

class SessionInput(BaseModel):
    session_id: str

class Director(BaseModel):
    name: str
    role: str = "Director"
    id_number: str = ""
    is_pep: bool = False
    ownership_pct: float = 0.0

class CompanyInput(BaseModel):
    legal_name: str
    brand_name: str = ""
    entity_type: str = "PT"
    nib: str = ""
    nib_expiry_date: str = ""  # ISO date YYYY-MM-DD, masa berlaku NIB
    npwp: str = ""
    deed_number: str = ""
    established_year: Optional[int] = None
    industry: str = "other"
    country: str = "Indonesia"
    address: str = ""
    website: str = ""
    annual_revenue_idr: float = 0.0
    paid_up_capital_idr: float = 0.0
    expected_monthly_volume_idr: float = 0.0
    source_of_funds: str = ""
    bank_name: str = ""
    bank_code: str = ""
    bank_account_number: str = ""
    bank_account_holder: str = ""
    directors: List[Director] = []

class DecisionInput(BaseModel):
    decision: str  # approved | rejected
    note: str = ""

# ---------------- Scoring engine ----------------
INDUSTRY_RISK = {
    "crypto_exchange": 90, "money_services": 85, "gambling": 95, "forex": 80,
    "fintech": 60, "trading": 55, "real_estate": 65, "ecommerce": 40,
    "manufacturing": 25, "technology": 30, "consulting": 25, "retail": 30,
    "logistics": 30, "mining": 55, "other": 50,
}

MOCK_WATCHLIST = [
    {"name": "Viktor Petrov", "type": "SANCTION", "list": "OFAC SDN"},
    {"name": "Budi Hartono Santoso", "type": "PEP", "list": "Domestic PEP - Regional Official"},
    {"name": "Ali Rahman", "type": "SANCTION", "list": "UN Consolidated"},
    {"name": "Global Shell Holdings", "type": "ADVERSE_MEDIA", "list": "Adverse Media - Fraud"},
    {"name": "Siti Nurhaliza Wijaya", "type": "PEP", "list": "Domestic PEP - Family"},
]

def _parse_date(s: str):
    if not s:
        return None
    try:
        s = s.strip().split("T")[0]
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def add_business_days(start: datetime, n: int) -> datetime:
    d = start
    added = 0
    while added < n:
        d = d + timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri
            added += 1
    return d

def _clean_nib(nib: str) -> str:
    return "".join(ch for ch in (nib or "") if ch.isdigit())

def validate_nib_format(nib: str) -> bool:
    return len(_clean_nib(nib)) == 13

def nib_registry_lookup(nib: str) -> dict:
    # Pluggable OSS/BKPM registry layer. Real provider active when NIB_REGISTRY_API_URL is configured.
    url = os.environ.get("NIB_REGISTRY_API_URL")
    if url:
        try:
            headers = {}
            key = os.environ.get("NIB_REGISTRY_API_KEY")
            if key:
                headers["Authorization"] = f"Bearer {key}"
            r = requests.get(url, params={"nib": _clean_nib(nib)}, headers=headers, timeout=20)
            r.raise_for_status()
            return {"source": "registry", "found": True, **r.json()}
        except Exception as e:
            logger.error(f"NIB registry lookup failed: {e}")
            return {"source": "registry", "found": False, "error": str(e)}
    # Simulation — siap dihubungkan ke provider OSS/BKPM nyata via NIB_REGISTRY_API_URL
    return {"source": "SIMULASI", "found": True, "status": "AKTIF", "note": "Registry OSS belum terhubung — data simulasi"}

def decode_nib_qr(image_bytes: bytes, expected_nib: str = "") -> dict:
    try:
        import re
        from urllib.parse import urlparse
        import cv2
        import numpy as np
        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return {"success": False, "reason": "Gambar tidak dapat dibaca"}
        detector = cv2.QRCodeDetector()
        data, points, _ = detector.detectAndDecode(img)
        if not data:
            return {"success": False, "reason": "QR code tidak terdeteksi pada dokumen"}
        host = (urlparse(data).hostname or "").lower()
        domain_valid = host == "oss.go.id" or host.endswith(".oss.go.id")
        m = re.search(r"\d{13}", data)
        nib_in_qr = m.group(0) if m else ""
        matches = (not expected_nib) or (nib_in_qr and _clean_nib(expected_nib) == nib_in_qr)
        return {"success": True, "raw": data[:300], "domain_valid": domain_valid, "nib_in_qr": nib_in_qr, "matches_input": bool(matches)}
    except Exception as e:
        logger.error(f"QR decode failed: {e}")
        return {"success": False, "reason": f"Gagal decode QR: {e}"}

def validate_nib(company: dict, qr: dict = None) -> dict:
    raw = company.get("nib") or ""
    nib = _clean_nib(raw)
    exp = _parse_date(company.get("nib_expiry_date"))
    today = datetime.now(timezone.utc).date()
    fmt = validate_nib_format(raw)
    result = {
        "nib_present": bool(nib), "format_valid": fmt,
        "nib_expiry_date": company.get("nib_expiry_date", ""),
        "expired": False, "valid": True, "reason": "", "qr": qr, "registry": None,
    }
    if not nib:
        result["valid"] = False
        result["reason"] = "NIB tidak diisi"
        return result
    if not fmt:
        result["valid"] = False
        result["reason"] = "Format NIB tidak valid (harus 13 digit)"
    result["registry"] = nib_registry_lookup(nib)
    if exp is None:
        result["valid"] = False
        if not result["reason"]:
            result["reason"] = "Tanggal masa berlaku NIB tidak valid / kosong"
    elif exp < today:
        result["expired"] = True
        result["valid"] = False
        result["reason"] = f"NIB telah kedaluwarsa pada {exp.isoformat()}"
    if qr and qr.get("success") and not qr.get("matches_input", True):
        result["valid"] = False
        if not result["reason"]:
            result["reason"] = "QR NIB tidak cocok dengan nomor NIB yang diinput"
    return result

def _name_similarity(a: str, b: str) -> float:
    a, b = (a or "").lower().strip(), (b or "").lower().strip()
    if not a or not b:
        return 0.0
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))

# ---------------- BRIAPI Account Name Validation (name-check) ----------------
_bri_token_cache = {"token": None, "exp": 0.0}

def _bri_get_token():
    cid = os.environ.get("BRI_CLIENT_ID")
    csec = os.environ.get("BRI_CLIENT_SECRET")
    base = os.environ.get("BRI_BASE_URL", "https://sandbox.partner.api.bri.co.id")
    if not (cid and csec):
        return None
    now = time.time()
    if _bri_token_cache["token"] and _bri_token_cache["exp"] > now + 30:
        return _bri_token_cache["token"]
    basic = base64.b64encode(f"{cid}:{csec}".encode()).decode()
    r = requests.post(
        f"{base}/oauth/client_credential/accesstoken", params={"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"}, timeout=20,
    )
    r.raise_for_status()
    d = r.json()
    _bri_token_cache["token"] = d.get("access_token")
    _bri_token_cache["exp"] = now + int(d.get("expires_in", 300) or 300)
    return _bri_token_cache["token"]

def _bri_signature(path: str, verb: str, token: str, timestamp: str, body: str, secret: str) -> str:
    import hmac, hashlib
    payload = f"path={path}&verb={verb}&token=Bearer {token}&timestamp={timestamp}&body={body}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

def bri_name_validation(bank_code: str, account_number: str) -> dict:
    cid = os.environ.get("BRI_CLIENT_ID")
    csec = os.environ.get("BRI_CLIENT_SECRET")
    base = os.environ.get("BRI_BASE_URL", "https://sandbox.partner.api.bri.co.id")
    if not (cid and csec):
        return {"source": "SIMULASI", "configured": False, "success": False}
    try:
        token = _bri_get_token()
        path = "/v1.0/validation-account/name-validate"
        body = json.dumps({"bankCode": bank_code or "014", "accountNumber": account_number}, separators=(",", ":"))
        n = datetime.now(timezone.utc)
        ts = n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"
        sig = _bri_signature(path, "POST", token, ts, body, csec)
        r = requests.post(f"{base}{path}", data=body, headers={
            "Authorization": f"Bearer {token}", "BRI-Timestamp": ts, "BRI-Signature": sig, "Content-Type": "application/json"}, timeout=25)
        d = r.json()
        ok = d.get("responseCode") == "0000"
        return {"source": "BRIAPI", "configured": True, "success": ok, "response_code": d.get("responseCode"),
                "response_description": d.get("responseDescription"), "account_name": (d.get("data") or {}).get("accountName", ""),
                "error": d.get("errorDescription", "")}
    except Exception as e:
        logger.error(f"BRIAPI name validation failed: {e}")
        return {"source": "BRIAPI", "configured": True, "success": False, "error": str(e)}

def verify_bank(company: dict) -> dict:
    bank_code = (company.get("bank_code") or "").strip()
    name = (company.get("bank_name") or "").strip()
    acc = (company.get("bank_account_number") or "").strip()
    holder = (company.get("bank_account_holder") or "").strip()
    legal = company.get("legal_name", "")
    brand = company.get("brand_name", "")
    result = {"bank_name": name, "bank_code": bank_code,
              "account_number_masked": ("•••• " + acc[-4:]) if len(acc) >= 4 else acc,
              "declared_holder": holder, "resolved_name": "", "verified": False,
              "name_match_score": 0, "status": "unverified", "note": "", "source": "SIMULASI"}
    if not acc:
        result["note"] = "Nomor rekening tidak diisi"
        return result
    bri = bri_name_validation(bank_code, acc)
    if bri.get("configured"):
        result["source"] = "BRIAPI"
        if not bri.get("success"):
            result["status"] = "failed"
            result["note"] = bri.get("error") or bri.get("response_description") or "Inquiry rekening gagal"
            return result
        resolved = bri.get("account_name", "") or ""
    else:
        # BRIAPI belum dikonfigurasi → mode simulasi memakai nama pemilik yang dideklarasikan
        resolved = holder
        result["note"] = "BRIAPI belum dikonfigurasi — verifikasi simulasi"
    result["resolved_name"] = resolved
    sim = max(_name_similarity(resolved, legal), _name_similarity(resolved, brand))
    result["name_match_score"] = round(sim * 100)
    if sim >= 0.5:
        result["verified"] = True
        result["status"] = "verified"
        if not result["note"] or result["note"].startswith("BRIAPI belum"):
            result["note"] = (result["note"] + " · " if result["note"] else "") + "Nama pemilik rekening cocok"
    else:
        result["status"] = "mismatch"
        result["note"] = (result["note"] + " · " if result["note"] else "") + "Nama pemilik rekening tidak cocok dengan perusahaan"
    return result

# ---------------- Didit KYC/KYB (hosted sessions) ----------------
def didit_create_session(vendor_data: str, callback_path: str, workflow_id: str = None, metadata: dict = None, expected_details: dict = None) -> dict:
    api_key = os.environ.get("DIDIT_API_KEY")
    wf = workflow_id or os.environ.get("DIDIT_WORKFLOW_ID")
    base = os.environ.get("DIDIT_BASE_URL", "https://verification.didit.me")
    if not (api_key and wf):
        if os.environ.get("DIDIT_DEMO_MODE"):
            return {"configured": True, "demo": True, "session_id": f"demo_{uuid.uuid4().hex[:12]}",
                    "url": f"{FRONTEND_URL}{callback_path}", "status": "In Progress",
                    "session_kind": "kyc" if ":dir:" in vendor_data else "business"}
        return {"configured": False}
    payload = {"workflow_id": wf, "vendor_data": vendor_data, "callback": f"{FRONTEND_URL}{callback_path}", "language": "id"}
    if metadata:
        payload["metadata"] = metadata
    if expected_details:
        payload["expected_details"] = expected_details
    try:
        r = requests.post(f"{base}/v3/session/", json=payload, headers={"x-api-key": api_key, "Content-Type": "application/json"}, timeout=25)
        r.raise_for_status()
        d = r.json()
        return {"configured": True, "session_id": d.get("session_id"), "url": d.get("url"), "status": d.get("status"), "session_kind": d.get("session_kind")}
    except Exception as e:
        logger.error(f"Didit create session failed: {e}")
        return {"configured": True, "error": str(e)}

def didit_get_decision(session_id: str) -> dict:
    api_key = os.environ.get("DIDIT_API_KEY")
    base = os.environ.get("DIDIT_BASE_URL", "https://verification.didit.me")
    if not api_key:
        if os.environ.get("DIDIT_DEMO_MODE"):
            return {"configured": True, "demo": True, "session_id": session_id, "status": "Approved",
                    "registry_status": "Approved (SIMULASI)", "company_name": None, "risk_level": "LOW", "aml_total_hits": 0}
        return {"configured": False}
    try:
        r = requests.get(f"{base}/v3/session/{session_id}/decision/", headers={"x-api-key": api_key, "Accept": "application/json"}, timeout=25)
        r.raise_for_status()
        d = r.json()
        reg = (d.get("registry_checks") or [{}])[0].get("company", {}) if d.get("registry_checks") else {}
        aml = d.get("aml_screenings") or []
        return {"configured": True, "session_id": session_id, "session_kind": d.get("session_kind"), "status": d.get("status"),
                "registry_status": reg.get("registry_status"), "company_name": reg.get("company_name"),
                "risk_level": reg.get("risk_level"), "aml_total_hits": sum((a.get("total_hits") or 0) for a in aml)}
    except Exception as e:
        logger.error(f"Didit decision failed: {e}")
        return {"configured": True, "error": str(e)}

def _shorten_floats(data):
    if isinstance(data, dict):
        return {k: _shorten_floats(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_shorten_floats(x) for x in data]
    if isinstance(data, float) and data.is_integer():
        return int(data)
    return data

def verify_didit_signature(body_json: dict, headers) -> bool:
    import hmac, hashlib
    secret = os.environ.get("DIDIT_WEBHOOK_SECRET")
    if not secret:
        return True  # no secret configured -> accept (dev/unconfigured)
    ts = headers.get("x-timestamp")
    if not ts:
        return False
    try:
        if abs(int(time.time()) - int(ts)) > 300:
            return False
    except ValueError:
        return False
    sig_v2 = headers.get("x-signature-v2")
    if sig_v2:
        canonical = json.dumps(_shorten_floats(body_json), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig_v2, expected):
            return True
    sig_simple = headers.get("x-signature-simple")
    if sig_simple:
        canonical = ":".join([str(body_json.get("timestamp", "")), str(body_json.get("session_id", "")), str(body_json.get("status", "")), str(body_json.get("webhook_type", ""))])
        expected = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig_simple, expected):
            return True
    return False

def generate_report_pdf(a: dict) -> bytes:
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=34 * mm, bottomMargin=20 * mm, leftMargin=16 * mm, rightMargin=16 * mm)
    ss = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=ss["Heading1"], fontSize=16, textColor=colors.HexColor("#0A0A0A"))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11, textColor=colors.HexColor("#2563EB"), spaceBefore=10)
    body = ss["BodyText"]
    small = ParagraphStyle("small", parent=body, fontSize=8, textColor=colors.grey)
    co = a.get("company", {})
    score = a.get("score") or {}
    val = a.get("validation") or {}
    didit = a.get("didit") or {}
    el = []
    el.append(Paragraph(f"ID: {a.get('id')} &nbsp;·&nbsp; Dibuat: {a.get('created_at','')[:19]} &nbsp;·&nbsp; Status: {a.get('status')}", small))
    el.append(Spacer(1, 6))

    el.append(Paragraph("Profil Perusahaan", h2))
    ci = [["Nama Legal", co.get("legal_name", "-")], ["Jenis / Industri", f"{co.get('entity_type','-')} · {co.get('industry','-')}"],
          ["NIB", co.get("nib", "-")], ["Masa berlaku NIB", co.get("nib_expiry_date", "-")], ["NPWP", co.get("npwp", "-")],
          ["Pendapatan Tahunan", rp_pdf(co.get("annual_revenue_idr"))], ["Modal Disetor", rp_pdf(co.get("paid_up_capital_idr"))]]
    el.append(_pdf_table(ci, Table, TableStyle, colors))

    el.append(Paragraph("Skor Kredit / Risiko", h2))
    si = [["Skor Akhir", str(score.get("final_score", "-"))], ["Tingkat Risiko", str(score.get("risk_level", "-"))],
          ["Legalitas (25%)", str(score.get("legality", "-"))], ["Keuangan (25%)", str(score.get("financial", "-"))],
          ["Screening AML (30%)", str(score.get("screening", "-"))], ["Industri (20%)", str(score.get("industry", "-"))],
          ["Rule-based / AI adj", f"{score.get('overall_rule','-')} / {score.get('ai_adjustment','-')}"]]
    el.append(_pdf_table(si, Table, TableStyle, colors))

    el.append(Paragraph("Validasi Sistem", h2))
    nib_v = val.get("nib") or {}
    bank_v = val.get("bank") or {}
    vi = [["NIB valid", str(nib_v.get("valid", "-"))], ["NIB kedaluwarsa", str(nib_v.get("expired", "-"))],
          ["Registry OSS", f"{(nib_v.get('registry') or {}).get('source','-')} · {(nib_v.get('registry') or {}).get('status','-')}"],
          ["Bank", f"{bank_v.get('bank_name','-')} {bank_v.get('account_number_masked','')}"],
          ["Bank verified", f"{bank_v.get('verified','-')} ({bank_v.get('name_match_score',0)}%) · {bank_v.get('source','-')}"]]
    el.append(_pdf_table(vi, Table, TableStyle, colors))

    el.append(Paragraph("Screening Sanksi / PEP / Adverse Media", h2))
    hits = a.get("screening_hits") or []
    if hits:
        data = [["Nama", "Tipe", "Daftar"]] + [[hh.get("matched_name", "-"), hh.get("type", "-"), hh.get("list", "-")] for hh in hits]
        el.append(_pdf_table(data, Table, TableStyle, colors, header=True))
    else:
        el.append(Paragraph("Tidak ada kecocokan watchlist.", body))

    el.append(Paragraph("Verifikasi Didit (KYC/KYB)", h2))
    if didit.get("session_id"):
        di = [["Session", didit.get("session_id", "-")], ["Status", didit.get("status", "-")],
              ["Registry", str(didit.get("registry_status", "-"))], ["Risk Didit", str(didit.get("risk_level", "-"))],
              ["AML hits", str(didit.get("aml_total_hits", "-"))]]
        el.append(_pdf_table(di, Table, TableStyle, colors))
    else:
        el.append(Paragraph("Belum ada sesi Didit.", body))

    el.append(Paragraph("Keputusan", h2))
    el.append(Paragraph(f"{a.get('decision') or a.get('status')} — {a.get('decided_by') or '-'} {('· ' + a.get('decision_note')) if a.get('decision_note') else ''} {('· ' + a.get('auto_reject_reason')) if a.get('auto_reject_reason') else ''}", body))
    el.append(Spacer(1, 12))
    el.append(Paragraph("Dokumen ini dihasilkan otomatis oleh CorpScore untuk keperluan arsip compliance.", small))
    def _kop(canvas, doc_):
        canvas.saveState()
        w, hgt = A4
        canvas.setFillColor(colors.HexColor("#0A0A0A"))
        canvas.rect(0, hgt - 26 * mm, w, 26 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#2563EB"))
        canvas.rect(16 * mm, hgt - 17.5 * mm, 6 * mm, 6 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawString(25 * mm, hgt - 15 * mm, "CorpScore")
        canvas.setFillColor(colors.HexColor("#9CA3AF"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(25 * mm, hgt - 20 * mm, "KYB & Credit Scoring Console — Laporan Risiko Compliance")
        canvas.setFillColor(colors.HexColor("#60A5FA"))
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawRightString(w - 16 * mm, hgt - 15 * mm, "RAHASIA / CONFIDENTIAL")
        canvas.setStrokeColor(colors.HexColor("#E5E7EB"))
        canvas.line(16 * mm, 15 * mm, w - 16 * mm, 15 * mm)
        canvas.setFillColor(colors.HexColor("#9CA3AF"))
        canvas.setFont("Helvetica", 7)
        canvas.drawString(16 * mm, 11 * mm, "CorpScore RegTech · Dokumen dihasilkan otomatis untuk arsip compliance")
        canvas.drawRightString(w - 16 * mm, 11 * mm, f"Hal. {doc_.page}")
        canvas.restoreState()
    doc.build(el, onFirstPage=_kop, onLaterPages=_kop)
    return buf.getvalue()

def rp_pdf(n):
    try:
        return "Rp " + f"{int(n or 0):,}".replace(",", ".")
    except Exception:
        return "Rp 0"

def _pdf_table(rows, Table, TableStyle, colors, header=False):
    t = Table(rows, colWidths=None, hAlign="LEFT")
    style = [("FONTSIZE", (0, 0), (-1, -1), 9), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4),
             ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB"))]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A0A0A")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    else:
        style += [("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151"))]
    t.setStyle(TableStyle(style))
    return t

def screen_watchlist(company: dict):
    hits = []
    candidates = [company.get("legal_name", ""), company.get("brand_name", "")]
    for d in company.get("directors", []):
        candidates.append(d.get("name", ""))
        if d.get("is_pep"):
            hits.append({"matched_name": d.get("name"), "type": "PEP", "list": "Self-declared PEP", "score": 100})
    for cand in candidates:
        if not cand:
            continue
        cl = cand.lower()
        for wl in MOCK_WATCHLIST:
            wln = wl["name"].lower()
            if cl and (cl in wln or wln in cl or _token_overlap(cl, wln)):
                hits.append({"matched_name": cand, "type": wl["type"], "list": wl["list"], "score": 92})
    # dedupe
    seen, out = set(), []
    for h in hits:
        k = (h["matched_name"], h["list"])
        if k not in seen:
            seen.add(k)
            out.append(h)
    return out

def _token_overlap(a: str, b: str) -> bool:
    ta, tb = set(a.split()), set(b.split())
    common = ta & tb
    return len([t for t in common if len(t) > 3]) >= 2

def compute_rule_score(company: dict, screening_hits: list) -> dict:
    # Legality (doc completeness + key IDs)
    legal_fields = [company.get("nib"), company.get("npwp"), company.get("deed_number"), company.get("legal_name"), company.get("address")]
    filled = sum(1 for f in legal_fields if f)
    legality = round((filled / len(legal_fields)) * 100)

    # Financial
    rev = company.get("annual_revenue_idr", 0) or 0
    cap = company.get("paid_up_capital_idr", 0) or 0
    year = company.get("established_year")
    now_year = datetime.now(timezone.utc).year
    age = (now_year - year) if year else 0
    fin = 0
    fin += min(40, (rev / 5_000_000_000) * 40) if rev else 0
    fin += min(30, (cap / 2_500_000_000) * 30) if cap else 0
    fin += min(30, (age / 10) * 30) if age else 0
    financial = round(min(100, fin))

    # Screening
    sanction_hits = [h for h in screening_hits if h["type"] == "SANCTION"]
    pep_hits = [h for h in screening_hits if h["type"] == "PEP"]
    adverse_hits = [h for h in screening_hits if h["type"] == "ADVERSE_MEDIA"]
    screening = 100
    screening -= len(sanction_hits) * 60
    screening -= len(adverse_hits) * 25
    screening -= len(pep_hits) * 15
    screening = max(0, screening)

    # Industry
    ir = INDUSTRY_RISK.get(company.get("industry", "other"), 50)
    industry = 100 - ir

    weights = {"legality": 0.25, "financial": 0.25, "screening": 0.30, "industry": 0.20}
    overall = round(legality * weights["legality"] + financial * weights["financial"] + screening * weights["screening"] + industry * weights["industry"])
    return {
        "legality": legality, "financial": financial, "screening": screening, "industry": industry,
        "overall_rule": overall, "weights": weights,
    }

def risk_level_from_score(score: int) -> str:
    if score >= 75:
        return "LOW"
    if score >= 50:
        return "MEDIUM"
    return "HIGH"

async def ai_risk_review(company: dict, rule: dict, screening_hits: list) -> dict:
    if not EMERGENT_LLM_KEY:
        return {}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        system = (
            "You are a senior AML/KYB compliance analyst at an Indonesian crypto exchange, applying banking-grade "
            "corporate onboarding standards (PPATK/OJK aligned). Assess the business risk profile and return STRICT JSON only."
        )
        prompt = {
            "company": company,
            "rule_based_scores": rule,
            "screening_hits": screening_hits,
            "instruction": (
                "Return JSON with keys: risk_adjustment (integer -15..15, negative = riskier), "
                "narrative (2-3 sentence executive summary in Indonesian), red_flags (array of short strings), "
                "recommended_edd (array of enhanced due diligence steps in Indonesian). Only JSON."
            ),
        }
        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"kyb-{uuid.uuid4().hex[:8]}", system_message=system).with_model("openai", "gpt-5.4")
        resp = await chat.send_message(UserMessage(text=json.dumps(prompt, default=str)))
        text = resp if isinstance(resp, str) else str(resp)
        text = text.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "", 1).strip()
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start:end + 1])
        adj = int(data.get("risk_adjustment", 0))
        data["risk_adjustment"] = max(-15, min(15, adj))
        return data
    except Exception as e:
        logger.error(f"AI review failed: {e}")
        return {"error": "AI review unavailable", "narrative": "Analisa AI tidak tersedia; skor mengacu pada model berbasis aturan."}

async def ai_extract_document(image_b64: str, doc_type: str) -> dict:
    if not EMERGENT_LLM_KEY:
        return {}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        system = "You extract structured data from Indonesian corporate documents. Return STRICT JSON only, no prose."
        prompt = (
            f"This is a '{doc_type}' document. Extract any of these fields you can read and return JSON: "
            "company_legal_name, nib, npwp, deed_number, established_year, address, director_names (array). "
            "Use empty string/array when not present. JSON only."
        )
        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"ext-{uuid.uuid4().hex[:8]}", system_message=system).with_model("openai", "gpt-5.4")
        resp = await chat.send_message(UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_b64)]))
        text = (resp if isinstance(resp, str) else str(resp)).strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "", 1).strip()
        s, e = text.find("{"), text.rfind("}")
        return json.loads(text[s:e + 1])
    except Exception as e:
        logger.error(f"AI extract failed: {e}")
        return {"error": "AI extraction unavailable"}

# ---------------- Auth routes ----------------
@api_router.post("/auth/register")
async def register(inp: RegisterInput, response: Response):
    email = inp.email.strip().lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    doc = {
        "user_id": user_id, "email": email, "name": inp.name.strip() or email,
        "role": "applicant", "password_hash": hash_password(inp.password),
        "picture": "", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(doc)
    token = create_access_token(user_id, email)
    set_auth_cookie(response, "access_token", token)
    return {"user_id": user_id, "email": email, "name": doc["name"], "role": "applicant", "token": token}

@api_router.post("/auth/login")
async def login(inp: LoginInput, response: Response):
    email = inp.email.strip().lower()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not verify_password(inp.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email atau kata sandi salah")
    token = create_access_token(user["user_id"], email)
    set_auth_cookie(response, "access_token", token)
    return {"user_id": user["user_id"], "email": email, "name": user.get("name"), "role": user.get("role"), "token": token}

@api_router.post("/auth/session")
async def google_session(inp: SessionInput, response: Response):
    r = requests.get("https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data", headers={"X-Session-ID": inp.session_id}, timeout=30)
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Sesi Google tidak valid")
    data = r.json()
    email = data["email"].strip().lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        role = "owner" if email == os.environ.get("ADMIN_EMAIL", "").lower() else "applicant"
        user = {"user_id": user_id, "email": email, "name": data.get("name", email), "role": role, "picture": data.get("picture", ""), "created_at": datetime.now(timezone.utc).isoformat()}
        await db.users.insert_one(dict(user))
    session_token = data["session_token"]
    await db.user_sessions.insert_one({"user_id": user["user_id"], "session_token": session_token, "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(), "created_at": datetime.now(timezone.utc).isoformat()})
    set_auth_cookie(response, "session_token", session_token)
    return {"user_id": user["user_id"], "email": email, "name": user.get("name"), "role": user.get("role"), "picture": user.get("picture", "")}

@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"user_id": user["user_id"], "email": user["email"], "name": user.get("name"), "role": user.get("role"), "picture": user.get("picture", "")}

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    stoken = request.cookies.get("session_token")
    if stoken:
        await db.user_sessions.delete_many({"session_token": stoken})
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("session_token", path="/")
    return {"ok": True}

# ---------------- Application routes ----------------
def serialize_app(a: dict) -> dict:
    a.pop("_id", None)
    return a

@api_router.post("/applications")
async def create_application(inp: CompanyInput, user: dict = Depends(get_current_user)):
    app_id = f"app_{uuid.uuid4().hex[:12]}"
    company = inp.model_dump()
    doc = {
        "id": app_id, "applicant_user_id": user["user_id"], "applicant_email": user["email"],
        "company": company, "documents": [], "status": "draft",
        "screening_hits": [], "score": None, "ai_review": None,
        "decision": None, "decision_note": "", "decided_by": None, "decided_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.applications.insert_one(dict(doc))
    return serialize_app(doc)

@api_router.get("/applications")
async def list_applications(user: dict = Depends(get_current_user)):
    query = {} if user.get("role") in ("owner", "officer") else {"applicant_user_id": user["user_id"]}
    apps = await db.applications.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return apps

@api_router.get("/applications/{app_id}")
async def get_application(app_id: str, user: dict = Depends(get_current_user)):
    a = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    if user.get("role") not in ("owner", "officer") and a["applicant_user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    return a

@api_router.put("/applications/{app_id}")
async def update_application(app_id: str, inp: CompanyInput, user: dict = Depends(get_current_user)):
    a = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    if user.get("role") not in ("owner", "officer") and a["applicant_user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    await db.applications.update_one({"id": app_id}, {"$set": {"company": inp.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}})
    return await db.applications.find_one({"id": app_id}, {"_id": 0})

@api_router.post("/applications/{app_id}/documents")
async def upload_document(app_id: str, doc_type: str = Form(...), file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    a = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    if user.get("role") not in ("owner", "officer") and a["applicant_user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    data = await file.read()
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
    path = f"{APP_NAME}/{app_id}/{uuid.uuid4().hex}.{ext}"
    ctype = file.content_type or "application/octet-stream"
    put_object(path, data, ctype)
    extracted = {}
    if ctype.startswith("image/"):
        extracted = await ai_extract_document(base64.b64encode(data).decode(), doc_type)
    doc = {
        "doc_id": uuid.uuid4().hex, "doc_type": doc_type, "storage_path": path,
        "original_filename": file.filename, "content_type": ctype, "size": len(data),
        "extracted": extracted, "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.applications.update_one({"id": app_id}, {"$push": {"documents": doc}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}})
    return doc

@api_router.get("/applications/{app_id}/documents/{doc_id}/download")
async def download_document(app_id: str, doc_id: str, request: Request, auth: str = Query(None)):
    user = await resolve_user(request)
    if not user and auth:
        try:
            payload = jwt.decode(auth, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0})
        except jwt.PyJWTError:
            sess = await db.user_sessions.find_one({"session_token": auth})
            if sess:
                user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    a = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    if user.get("role") not in ("owner", "officer") and a["applicant_user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    doc = next((d for d in a.get("documents", []) if d["doc_id"] == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    content, ctype = get_object(doc["storage_path"])
    return Response(content=content, media_type=doc.get("content_type", ctype))

@api_router.post("/applications/{app_id}/didit/session")
async def didit_session_endpoint(app_id: str, user: dict = Depends(get_current_user)):
    a = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    if user.get("role") not in ("owner", "officer") and a["applicant_user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    company = a.get("company", {})
    res = didit_create_session(
        vendor_data=a["id"], callback_path=f"/applications/{a['id']}",
        metadata={"legal_name": company.get("legal_name", ""), "nib": company.get("nib", "")},
        expected_details={"company_name": company.get("legal_name", ""), "registry_country": "ID", "registration_number": company.get("nib", "")},
    )
    if res.get("session_id"):
        await db.applications.update_one({"id": app_id}, {"$set": {"didit": res, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return res

@api_router.get("/applications/{app_id}/didit/decision")
async def didit_decision_endpoint(app_id: str, user: dict = Depends(get_current_user)):
    a = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    if user.get("role") not in ("owner", "officer") and a["applicant_user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    sid = (a.get("didit") or {}).get("session_id")
    if not sid:
        raise HTTPException(status_code=400, detail="Sesi Didit belum dibuat")
    res = didit_get_decision(sid)
    await db.applications.update_one({"id": app_id}, {"$set": {"didit": {**(a.get("didit") or {}), **res}, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return res

@api_router.post("/applications/{app_id}/directors/{index}/didit-session")
async def director_kyc_session(app_id: str, index: int, user: dict = Depends(get_current_user)):
    a = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    if user.get("role") not in ("owner", "officer") and a["applicant_user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    directors = (a.get("company") or {}).get("directors") or []
    if index < 0 or index >= len(directors):
        raise HTTPException(status_code=404, detail="Direktur tidak ditemukan")
    d = directors[index]
    res = didit_create_session(
        vendor_data=f"{app_id}:dir:{index}", callback_path=f"/applications/{app_id}",
        workflow_id=os.environ.get("DIDIT_KYC_WORKFLOW_ID"),
        metadata={"app": app_id, "director_index": index, "director_name": d.get("name", "")},
    )
    if res.get("session_id"):
        dk = a.get("director_kyc") or {}
        dk[str(index)] = {"name": d.get("name", ""), "session_id": res.get("session_id"), "url": res.get("url"), "status": res.get("status") or "Not Started"}
        await db.applications.update_one({"id": app_id}, {"$set": {"director_kyc": dk, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return res

@api_router.get("/applications/{app_id}/didit/events")
async def didit_events(app_id: str, user: dict = Depends(get_current_user)):
    a = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    if user.get("role") not in ("owner", "officer") and a["applicant_user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    return await db.didit_events.find({"app_id": app_id}, {"_id": 0}).sort("received_at", -1).to_list(200)

@api_router.post("/didit/webhook")
async def didit_webhook(request: Request):
    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid body")
    verified = verify_didit_signature(payload, request.headers)
    vendor = payload.get("vendor_data") or ""
    base_app_id = vendor.split(":dir:")[0] if vendor else ""
    await db.didit_events.insert_one({
        "event_id": payload.get("event_id"), "app_id": base_app_id, "vendor_data": vendor,
        "webhook_type": payload.get("webhook_type"), "status": payload.get("status"),
        "session_id": payload.get("session_id"), "session_kind": payload.get("session_kind"),
        "verified": verified, "environment": payload.get("environment"),
        "received_at": datetime.now(timezone.utc).isoformat(),
    })
    if not verified:
        raise HTTPException(status_code=401, detail="Invalid signature")
    if payload.get("webhook_type") not in ("status.updated", "data.updated"):
        return {"ok": True}
    status = payload.get("status")
    if not vendor:
        return {"ok": True}
    if ":dir:" in vendor:
        idx = vendor.split(":dir:")[1]
        a = await db.applications.find_one({"id": base_app_id}, {"_id": 0})
        if not a:
            return {"ok": True}
        dk = a.get("director_kyc") or {}
        entry = dk.get(idx) or {}
        entry.update({"session_id": payload.get("session_id"), "status": status})
        dk[idx] = entry
        await db.applications.update_one({"id": base_app_id}, {"$set": {"director_kyc": dk, "updated_at": datetime.now(timezone.utc).isoformat()}})
        return {"ok": True}
    a = await db.applications.find_one({"id": base_app_id}, {"_id": 0})
    if not a:
        return {"ok": True}
    didit = {**(a.get("didit") or {}), "session_id": payload.get("session_id"), "status": status,
             "session_kind": payload.get("session_kind"), "last_event_id": payload.get("event_id")}
    update = {"didit": didit, "updated_at": datetime.now(timezone.utc).isoformat()}
    if status == "Approved" and a.get("status") not in ("approved", "rejected", "auto_rejected"):
        update.update({"status": "approved", "decision": "approved", "decided_by": "SYSTEM (Didit)",
                       "decision_note": "Auto-approved via Didit verification", "decided_at": datetime.now(timezone.utc).isoformat()})
    elif status == "Declined" and a.get("status") not in ("approved", "rejected", "auto_rejected"):
        update.update({"status": "rejected", "decision": "rejected", "decided_by": "SYSTEM (Didit)",
                       "decision_note": "Auto-declined via Didit verification", "decided_at": datetime.now(timezone.utc).isoformat()})
    await db.applications.update_one({"id": base_app_id}, {"$set": update})
    return {"ok": True}

@api_router.get("/applications/{app_id}/report.pdf")
async def report_pdf(app_id: str, user: dict = Depends(get_current_user)):
    a = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    if user.get("role") not in ("owner", "officer") and a["applicant_user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    pdf = generate_report_pdf(a)
    fname = f"KYB_{(a.get('company') or {}).get('legal_name','report').replace(' ', '_')}.pdf"
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=\"{fname}\""})

@api_router.post("/applications/{app_id}/verify-nib")
async def verify_nib_endpoint(app_id: str, file: UploadFile = File(None), user: dict = Depends(get_current_user)):
    a = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    if user.get("role") not in ("owner", "officer") and a["applicant_user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    company = a["company"]
    qr = None
    if file is not None:
        data = await file.read()
        qr = decode_nib_qr(data, company.get("nib", ""))
    nib_val = validate_nib(company, qr)
    await db.applications.update_one({"id": app_id}, {"$set": {"nib_qr": qr, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"nib": nib_val, "qr": qr}

@api_router.post("/applications/{app_id}/verify-bank")
async def verify_bank_endpoint(app_id: str, user: dict = Depends(get_current_user)):
    a = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    if user.get("role") not in ("owner", "officer") and a["applicant_user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    return {"bank": verify_bank(a["company"])}

@api_router.post("/applications/{app_id}/submit")
async def submit_application(app_id: str, user: dict = Depends(get_current_user)):
    a = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    if user.get("role") not in ("owner", "officer") and a["applicant_user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    if a.get("status") in ("auto_rejected", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="Aplikasi sudah difinalisasi dan tidak dapat dikirim ulang")
    company = a["company"]
    nib_val = validate_nib(company, a.get("nib_qr"))
    bank_val = verify_bank(company)
    hits = screen_watchlist(company)
    rule = compute_rule_score(company, hits)
    ai = await ai_risk_review(company, rule, hits)
    final = max(0, min(100, rule["overall_rule"] + int(ai.get("risk_adjustment", 0) or 0)))
    score = {
        **rule, "ai_adjustment": int(ai.get("risk_adjustment", 0) or 0),
        "final_score": final, "risk_level": risk_level_from_score(final),
    }
    now = datetime.now(timezone.utc)
    validation = {"nib": nib_val, "bank": bank_val}
    update = {
        "status": "under_review", "screening_hits": hits, "score": score, "ai_review": ai,
        "validation": validation, "submitted_at": now.isoformat(), "updated_at": now.isoformat(),
        "sla_due_at": None, "sla_days": None, "auto_reject_reason": None,
    }
    # Auto-rejection: NIB expired / invalid masa berlaku
    if nib_val["expired"] or not nib_val["valid"]:
        update["status"] = "auto_rejected"
        update["decision"] = "auto_rejected"
        update["auto_reject_reason"] = nib_val["reason"]
        update["decided_by"] = "SYSTEM (validasi otomatis)"
        update["decided_at"] = now.isoformat()
    else:
        # Valid → antrean peninjauan manual dengan SLA 3 hari kerja
        sla_due = add_business_days(now, 3)
        update["sla_due_at"] = sla_due.isoformat()
        update["sla_days"] = 3
    await db.applications.update_one({"id": app_id}, {"$set": update})
    return await db.applications.find_one({"id": app_id}, {"_id": 0})

@api_router.post("/applications/{app_id}/decision")
async def decide_application(app_id: str, inp: DecisionInput, user: dict = Depends(get_current_user)):
    require_officer(user)
    if inp.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Keputusan tidak valid")
    a = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    await db.applications.update_one({"id": app_id}, {"$set": {
        "status": inp.decision, "decision": inp.decision, "decision_note": inp.note,
        "decided_by": user["email"], "decided_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    return await db.applications.find_one({"id": app_id}, {"_id": 0})

@api_router.get("/dashboard/stats")
async def dashboard_stats(user: dict = Depends(get_current_user)):
    query = {} if user.get("role") in ("owner", "officer") else {"applicant_user_id": user["user_id"]}
    apps = await db.applications.find(query, {"_id": 0}).to_list(1000)
    total = len(apps)
    by_status = {}
    risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    scored = []
    for a in apps:
        by_status[a["status"]] = by_status.get(a["status"], 0) + 1
        if a.get("score"):
            risk_counts[a["score"]["risk_level"]] = risk_counts.get(a["score"]["risk_level"], 0) + 1
            scored.append(a["score"]["final_score"])
    return {
        "total": total, "by_status": by_status, "risk_counts": risk_counts,
        "pending_review": by_status.get("under_review", 0),
        "avg_score": round(sum(scored) / len(scored)) if scored else 0,
    }

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=[FRONTEND_URL, "http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id")
    await db.applications.create_index("id")
    await db.user_sessions.create_index("session_token")
    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    admin_email = os.environ.get("ADMIN_EMAIL", "").lower()
    admin_pw = os.environ.get("ADMIN_PASSWORD", "")
    if admin_email:
        existing = await db.users.find_one({"email": admin_email})
        if not existing:
            await db.users.insert_one({"user_id": f"user_{uuid.uuid4().hex[:12]}", "email": admin_email, "name": "Compliance Owner", "role": "owner", "password_hash": hash_password(admin_pw), "picture": "", "created_at": datetime.now(timezone.utc).isoformat()})
        else:
            update = {"role": "owner"}
            if admin_pw and not verify_password(admin_pw, existing.get("password_hash", "")):
                update["password_hash"] = hash_password(admin_pw)
            await db.users.update_one({"email": admin_email}, {"$set": update})

@app.on_event("shutdown")
async def shutdown():
    client.close()
