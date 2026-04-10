"""
Supabase REST Client — Bharat OPD cloud database wrapper.
Supabase ka PostgREST API use karke CRUD operations karta hai.
"""

import logging

import requests

from config import settings

log = logging.getLogger(__name__)


def _headers() -> dict[str, str]:
    """Supabase ke liye required HTTP headers banata hai."""
    return {
        "apikey": settings.SUPABASE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _base() -> str:
    return f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1"


def is_configured() -> bool:
    """Supabase URL aur key dono non-empty hain to True return karta hai."""
    return bool(settings.SUPABASE_URL and settings.SUPABASE_KEY)


def insert_row(table: str, data: dict) -> dict | None:
    """Naya row insert karta hai — POST request se."""
    if not is_configured():
        log.warning("Supabase not configured, skipping insert.")
        return None
    try:
        url = f"{_base()}/{table}"
        resp = requests.post(url, json=data, headers=_headers(), timeout=15)
        resp.raise_for_status()
        result = resp.json()
        return result[0] if isinstance(result, list) else result
    except requests.RequestException as e:
        log.error("insert_row [%s]: %s", table, e)
        return None


def fetch_rows(table: str, filters: dict | None = None) -> list[dict]:
    """Rows fetch karta hai — optional filters ke saath GET request."""
    if not is_configured():
        log.warning("Supabase not configured, skipping fetch.")
        return []
    try:
        url = f"{_base()}/{table}"
        params: dict = {}
        if filters:
            # filters dict ko query params mein convert karta hai
            for k, v in filters.items():
                params[k] = f"eq.{v}"
        resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        log.error("fetch_rows [%s]: %s", table, e)
        return []


def update_row(table: str, row_id: str, data: dict) -> bool:
    """Row update karta hai — PATCH request se, id filter ke saath."""
    if not is_configured():
        log.warning("Supabase not configured, skipping update.")
        return False
    try:
        url = f"{_base()}/{table}"
        params = {"id": f"eq.{row_id}"}
        resp = requests.patch(url, json=data, headers=_headers(), params=params, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error("update_row [%s][%s]: %s", table, row_id, e)
        return False


def delete_row(table: str, row_id: str) -> bool:
    """Row delete karta hai — DELETE request se, id filter ke saath."""
    if not is_configured():
        log.warning("Supabase not configured, skipping delete.")
        return False
    try:
        url = f"{_base()}/{table}"
        params = {"id": f"eq.{row_id}"}
        resp = requests.delete(url, headers=_headers(), params=params, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error("delete_row [%s][%s]: %s", table, row_id, e)
        return False


def init_tables() -> bool:
    """Supabase RPC call se tables initialise karne ka attempt karta hai.
    Agar RPC fail ho to bhi True return karta hai kyunki tables manually bhi ho sakte hain."""
    if not is_configured():
        log.info("Supabase not configured — skipping init_tables.")
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
