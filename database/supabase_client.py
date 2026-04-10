"""
supabase_client — Bharat OPD cloud database wrapper.
Supabase ka PostgREST API use karke CRUD operations karta hai.
No external dependencies — uses requests library only.
"""

import logging
import requests
import config.settings as settings

log = logging.getLogger(__name__)


def _supa_available() -> bool:
    """Check if Supabase is configured (URL + Key both non-empty)."""
    url = settings.SUPABASE_URL
    key = settings.SUPABASE_KEY
    if not url or not key:
        return False
    return True


def is_configured() -> bool:
    """Public alias for _supa_available."""
    return _supa_available()


def _headers() -> dict:
    """Supabase REST API headers with API key and auth token."""
    return {
        "apikey": settings.SUPABASE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _base() -> str:
    """Supabase REST API base URL."""
    return f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1"


def supa_insert(table: str, data: dict) -> dict:
    """Insert a row via POST request. Returns the inserted row or error dict."""
    if not _supa_available():
        return {"error": "Supabase not configured"}
    try:
        url = f"{_base()}/{table}"
        resp = requests.post(url, json=data, headers=_headers(), timeout=15)
        resp.raise_for_status()
        result = resp.json()
        return result[0] if isinstance(result, list) else result
    except requests.RequestException as e:
        log.error("supa_insert [%s]: %s", table, e)
        return {"error": str(e)}


def supa_select(table: str, filters: dict = None, limit: int = 100) -> list:
    """Fetch rows via GET request. Optional filters dict."""
    if not _supa_available():
        return []
    try:
        url = f"{_base()}/{table}"
        params = {}
        if filters:
            for k, v in filters.items():
                params[k] = f"eq.{v}"
        params["limit"] = str(limit)
        params["order"] = "id.desc"
        resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        log.error("supa_select [%s]: %s", table, e)
        return []


def supa_update(table: str, row_id: str, data: dict) -> bool:
    """Update a row via PATCH request."""
    if not _supa_available():
        return False
    try:
        url = f"{_base()}/{table}"
        params = {"id": f"eq.{row_id}"}
        resp = requests.patch(url, json=data, headers=_headers(), params=params, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error("supa_update [%s][%s]: %s", table, row_id, e)
        return False


def init_tables() -> bool:
    """Try to init Supabase tables via RPC. Returns True if successful."""
    if not _supa_available():
        return False
    try:
        url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/rpc/init_opd_tables"
        resp = requests.post(url, json={}, headers=_headers(), timeout=15)
        resp.raise_for_status()
        log.info("Supabase tables initialised via RPC.")
        return True
    except requests.RequestException as e:
        log.warning("init_tables RPC failed (tables may already exist): %s", e)
        return False


def push_patient_to_supabase(patient_data: dict) -> bool:
    """Push a patient record to Supabase 'patients' table."""
    return supa_insert("patients", patient_data).get("error") is None
