"""Sync Manager — Supabase-to-local sync, Google Sheet import, duplicate detection."""
import csv, io, logging
import requests
import database.sqlite_client as db
import database.supabase_client as sb
from config import settings

log = logging.getLogger(__name__)

def sync_supabase_to_local() -> dict:
    """Supabase se patients pull karke SQLite mein upsert — return {"synced": N, "errors": [...]}"""
    result: dict = {"synced": 0, "errors": []}
    if not sb.is_configured():
        result["errors"].append("Supabase not configured."); return result
    try:
        remote = sb.fetch_rows("patients")
        for row in remote:
            try:
                data = {"name": row.get("name",""), "age": row.get("age",""),
                    "gender": row.get("gender",""), "phone": row.get("phone",""),
                    "address": row.get("address","")}
                if db.get_patient_by_id(int(row.get("id", 0))):
                    db.update_patient(int(row["id"]), data)
                else:
                    db.insert_patient(data)
                result["synced"] += 1
            except Exception as ex: result["errors"].append(f"Row {row.get('id')}: {ex}")
        log.info("Sync complete — %d patients.", result["synced"])
    except Exception as e: result["errors"].append(str(e)); log.error("sync: %s", e)
    return result

def fetch_google_sheet() -> list[dict]:
    """Google Sheets CSV export se patient records fetch karta hai."""
    if not settings.GOOGLE_SHEET_ID:
        log.warning("Google Sheet ID not configured."); return []
    try:
        url = f"https://docs.google.com/spreadsheets/d/{settings.GOOGLE_SHEET_ID}/export?format=csv"
        resp = requests.get(url, timeout=20); resp.raise_for_status()
        # CSV ko DictReader se parse karte hain — standard library csv module
        reader = csv.DictReader(io.StringIO(resp.text))
        return [{"name": (r.get("name") or "").strip(), "age": (r.get("age") or "").strip(),
                 "gender": (r.get("gender") or "").strip(), "phone": (r.get("phone") or "").strip(),
                 "address": (r.get("address") or "").strip()} for r in reader]
    except requests.RequestException as e: log.error("fetch_google_sheet: %s", e); return []

def detect_duplicates(patients: list[dict]) -> list[dict]:
    """Phone number se duplicates dhundta hai — both batch-level aur DB-level check."""
    dupes: list[dict] = []
    seen: set[str] = set()
    for p in patients:
        phone = (p.get("phone") or "").strip()
        if not phone: continue
        # Pehle batch mein check — ek hi import mein repeat phone?
        if phone in seen:
            dupes.append({**p, "reason": "duplicate_in_batch"}); continue
        seen.add(phone)
        # Ab local DB mein check — same phone already registered?
        local = db.search_patients(phone)
        if local:
            dupes.append({**p, "reason": "phone_exists_in_db",
                "existing_id": local[0].get("id"), "existing_name": local[0].get("name")})
    log.info("Duplicates: %d in %d records.", len(dupes), len(patients))
    return dupes

def restore_backup() -> bool:
    """Supabase se patients + drugs restore karta hai — True/False."""
    if not sb.is_configured():
        log.error("restore_backup: Supabase not configured."); return False
    try:
        for row in sb.fetch_rows("patients"):
            data = {"name": row.get("name",""), "age": row.get("age",""),
                "gender": row.get("gender",""), "phone": row.get("phone",""),
                "address": row.get("address","")}
            if not db.search_patients(row.get("phone","")):
                db.insert_patient(data)
        for row in sb.fetch_rows("drugs"):
            db.insert_drug(row.get("name",""), row.get("category",""))
        log.info("Backup restore complete."); return True
    except Exception as e: log.error("restore_backup: %s", e); return False
