"""
sync_manager — Supabase-to-local sync, Google Sheets backup, cloud restore.
Handles data synchronization between local SQLite and cloud sources.
"""

import csv
import io
import json
import logging
import requests
import re
from datetime import datetime, date, timedelta

import database.sqlite_client as db
import database.supabase_client as sb
import config.settings as settings

log = logging.getLogger(__name__)


def sync_from_supabase():
    """
    On login: pull fresh data from Supabase and merge into local SQLite.
    Only runs if Supabase is configured. Non-blocking.
    """
    if not sb._supa_available():
        return

    try:
        # Pull last 30 days of data from Supabase
        since = (date.today() - timedelta(days=30)).isoformat()
        remote = sb.supa_select("patients", filters={"doctor_id": settings.PINS.get("chief", "chief")}, limit=200)
        synced = 0
        for row in remote:
            try:
                name = row.get("patient_name", "")
                phone = str(row.get("phone", ""))
                # Check if this patient already exists locally (same name + date)
                existing = db.search_patients(name)
                row_date = str(row.get("date", ""))[:10]
                dup = False
                for ex in existing:
                    if str(ex.get("date", ""))[:10] == row_date and ex.get("patient_name", "").lower() == name.lower():
                        dup = True
                        break
                if not dup and name:
                    db.save_patient(
                        patient_name=name,
                        phone=phone,
                        vitals=row.get("vitals", ""),
                        fee=str(row.get("fee", "300")),
                        complaints=row.get("complaints", ""),
                        medicines=row.get("medicines", ""),
                        investigations=row.get("investigations", ""),
                        specialty=row.get("specialty", "General Physician"),
                        doctor_id=row.get("doctor_id", "chief"),
                    )
                    synced += 1
            except Exception:
                pass
        if synced > 0:
            log.info("Synced %d records from Supabase.", synced)
    except Exception as e:
        log.error("sync_from_supabase error: %s", e)


def fetch_sheet_data(max_rows=500):
    """
    Fetch patient data from Google Sheets CSV export.
    Returns (list_of_dicts, total_count).
    Used for OPD roster and patient search merge.
    """
    webhook = settings.GOOGLE_SHEET_WEBHOOK
    if not webhook:
        return [], 0

    try:
        # Try fetching from Google Sheets CSV export
        sheet_id = settings.GOOGLE_SHEET_ID
        if sheet_id:
            url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
            resp = requests.get(url, timeout=20)
            if resp.status_code == 200:
                return _parse_sheet_csv(resp.text, max_rows)

        return [], 0
    except requests.RequestException as e:
        log.error("fetch_sheet_data error: %s", e)
        return [], 0


def _parse_sheet_csv(csv_text: str, max_rows: int = 500) -> tuple:
    """Parse Google Sheet CSV export into list of dicts."""
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = []
        for row in reader:
            r = {
                "patient_name": row.get("patient_name", row.get("name", row.get("Patient Name", ""))),
                "phone": str(row.get("phone", row.get("Phone", row.get("mobile", "")))),
                "vitals": row.get("vitals", row.get("Vitals", row.get("bp", ""))),
                "fee": str(row.get("fee", row.get("Fee", row.get("amount", "0")))),
                "date": str(row.get("date", row.get("Date", row.get("datetime", ""))))[:10],
                "complaints": row.get("complaints", row.get("Complaints", "")),
                "medicines": row.get("medicines", row.get("Medicines", row.get("prescription", row.get("Rx", "")))),
                "specialty": row.get("specialty", "GP"),
                "_source": "sheet",
            }
            # Clean empty keys
            r = {k: (v or "") for k, v in r.items()}
            if r.get("patient_name"):
                rows.append(r)
        return rows[:max_rows], len(rows)
    except Exception as e:
        log.error("_parse_sheet_csv error: %s", e)
        return [], 0


def restore_from_cloud(doctor_id="chief"):
    """
    Restore all patient data from Supabase to local SQLite.
    Called when local DB is empty after server restart.
    Returns list of restored records.
    """
    if not sb._supa_available():
        return []

    restored = []
    try:
        remote = sb.supa_select("patients", limit=1000)
        for row in remote:
            try:
                name = row.get("patient_name", "")
                if not name:
                    continue
                db.save_patient(
                    patient_name=name,
                    phone=str(row.get("phone", "")),
                    vitals=row.get("vitals", ""),
                    fee=str(row.get("fee", "300")),
                    complaints=row.get("complaints", ""),
                    medicines=row.get("medicines", ""),
                    investigations=row.get("investigations", ""),
                    specialty=row.get("specialty", "General Physician"),
                    doctor_id=row.get("doctor_id", doctor_id),
                )
                restored.append(name)
            except Exception:
                pass
        log.info("restore_from_cloud: %d records restored for %s", len(restored), doctor_id)
    except Exception as e:
        log.error("restore_from_cloud error: %s", e)
    return restored
