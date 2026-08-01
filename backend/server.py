from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import json
import base64
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

def validate_nib(company: dict) -> dict:
    nib = (company.get("nib") or "").strip()
    exp = _parse_date(company.get("nib_expiry_date"))
    today = datetime.now(timezone.utc).date()
    result = {"nib_present": bool(nib), "nib_expiry_date": company.get("nib_expiry_date", ""), "expired": False, "valid": True, "reason": ""}
    if not nib:
        result["valid"] = False
        result["reason"] = "NIB tidak diisi"
        return result
    if exp is None:
        result["valid"] = False
        result["reason"] = "Tanggal masa berlaku NIB tidak valid / kosong"
        return result
    if exp < today:
        result["expired"] = True
        result["valid"] = False
        result["reason"] = f"NIB telah kedaluwarsa pada {exp.isoformat()}"
    return result

def _name_similarity(a: str, b: str) -> float:
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return 0.0
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))

def verify_bank(company: dict) -> dict:
    name = (company.get("bank_name") or "").strip()
    acc = (company.get("bank_account_number") or "").strip()
    holder = (company.get("bank_account_holder") or "").strip()
    result = {"bank_name": name, "account_number_masked": ("•••• " + acc[-4:]) if len(acc) >= 4 else acc, "account_holder": holder, "verified": False, "name_match_score": 0, "status": "unverified", "note": ""}
    if not (name and acc and holder):
        result["note"] = "Data rekening tidak lengkap"
        return result
    legal = company.get("legal_name", "")
    brand = company.get("brand_name", "")
    sim = max(_name_similarity(holder, legal), _name_similarity(holder, brand))
    result["name_match_score"] = round(sim * 100)
    if sim >= 0.5:
        result["verified"] = True
        result["status"] = "verified"
        result["note"] = "Nama pemilik rekening cocok dengan nama perusahaan"
    else:
        result["status"] = "mismatch"
        result["note"] = "Nama pemilik rekening tidak cocok dengan nama perusahaan — perlu peninjauan manual"
    return result

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
    nib_val = validate_nib(company)
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
