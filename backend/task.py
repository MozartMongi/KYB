"""Celery tasks for OSS NIB Browserbase lookups."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient

from celery_app import celery_app
from automation import run_oss_nib_lookup, registry_from_oss_result

load_dotenv(Path(__file__).parent / ".env")
logger = logging.getLogger("kyb.task")


def _sync_db():
    mongo_url = os.environ["MONGO_URL"]
    client = MongoClient(
        mongo_url,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=8000,
    )
    return client, client[os.environ["DB_NAME"]]


def save_oss_registry_sync(app_id: str, result: dict) -> dict:
    """Persist OSS lookup onto the application document (sync pymongo)."""
    registry = registry_from_oss_result(result)
    now = datetime.now(timezone.utc).isoformat()
    client, db = _sync_db()
    try:
        db.applications.update_one(
            {"id": app_id},
            {"$set": {
                "validation.nib.registry": registry,
                "updated_at": now,
            }},
        )
    finally:
        client.close()
    return registry


@celery_app.task(name="run_oss_nib_job", bind=True, max_retries=1)
def run_oss_nib_job(self, app_id: str, nib: str):
    """Background: scrape oss.go.id for NIB detail and store on the application."""
    client, db = _sync_db()
    try:
        db.applications.update_one(
            {"id": app_id},
            {"$set": {
                "validation.nib.registry.lookup_status": "processing",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
    finally:
        client.close()

    result = run_oss_nib_lookup(nib)
    registry = save_oss_registry_sync(app_id, result)
    logger.info("OSS NIB job finished app=%s success=%s", app_id, result.get("success"))
    return {"app_id": app_id, "registry": registry}


# Backward-compatible alias from the Browserbase guide template
@celery_app.task(name="run_agent_job")
def run_agent_job(job_id: str, user_id: str, input_data: dict):
    app_id = job_id
    result = run_oss_nib_lookup((input_data or {}).get("nib") or "")
    save_oss_registry_sync(app_id, result)
    return result
