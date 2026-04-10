"""
sqlite_client — Bharat OPD local database (SQLite).
ALL database operations: patients, prescriptions, templates, licenses,
settings, pending batch scan records, drug suggestions, starred upgrades.

FIXED: Connection is never closed — cached globally for Streamlit lifetime.
_conn() auto-reconnects if connection is lost.
"""

import json
import logging
import sqlite3
from datetime import datetime, date, timedelta
from typing import Optional

from config.settings import PINS, DB_PATH

log = logging.getLogger(__name__)

# ── Schema — ALL tables ek saath create hote hain ──────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id TEXT NOT NULL DEFAULT 'chief',
    patient_name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    vitals TEXT DEFAULT '',
    fee TEXT DEFAULT '300',
    complaints TEXT DEFAULT '',
    medicines TEXT DEFAULT '',
    investigations TEXT DEFAULT '',
    specialty TEXT DEFAULT 'General Physician',
    date TEXT DEFAULT (datetime('now','localtime')),
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS pending_rx (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id TEXT NOT NULL DEFAULT 'chief',
    image_b64 TEXT DEFAULT '',
    ai_extracted TEXT DEFAULT '',
    patient_name TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    vitals TEXT DEFAULT '',
    fee TEXT DEFAULT '300',
    complaints TEXT DEFAULT '',
    medicines TEXT DEFAULT '',
    investigations TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    uploaded_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS specialty_upgrades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_name TEXT NOT NULL,
    vitals TEXT DEFAULT '',
    original_rx TEXT DEFAULT '',
    specialty TEXT DEFAULT '',
    upgraded_rx TEXT DEFAULT '',
    evidence TEXT DEFAULT '',
    star_note TEXT DEFAULT '',
    starred INTEGER DEFAULT 0,
    date TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS drug_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id TEXT NOT NULL DEFAULT 'chief',
    drug_name TEXT NOT NULL,
    date TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL DEFAULT 'Rx',
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id TEXT UNIQUE NOT NULL,
    doctor_name TEXT NOT NULL,
    doctor_email TEXT DEFAULT '',
    doctor_phone TEXT DEFAULT '',
    pin TEXT NOT NULL,
    clinic_name TEXT DEFAULT '',
    specialty TEXT DEFAULT '',
    expiry_date TEXT NOT NULL,
    notes TEXT DEFAULT '',
    created_date TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

# ── Connection helper — NEVER close, auto-reconnect ───────────────────────
_conn_cache = None


def _conn() -> sqlite3.Connection:
    """Get or create a cached SQLite connection. Auto-reconnects if dead."""
    global _conn_cache
    try:
        if _conn_cache is not None:
            # Quick health check — if connection is closed or broken, recreate
            _conn_cache.execute("SELECT 1")
            return _conn_cache
    except Exception:
        _conn_cache = None

    _conn_cache = sqlite3.connect(DB_PATH, check_same_thread=False)
    _conn_cache.row_factory = sqlite3.Row
    _conn_cache.execute("PRAGMA journal_mode=WAL")
    return _conn_cache


# ── Init ────────────────────────────────────────────────────────────────────
def init_db():
    """Create all tables if they don't exist."""
    try:
        c = _conn()
        c.executescript(_SCHEMA)
        c.commit()
        log.info("SQLite tables initialised successfully.")
    except Exception as e:
        log.error("init_db error: %s", e)


# ── Settings ────────────────────────────────────────────────────────────────
def get_settings() -> dict:
    """Get all app settings as dict. Returns defaults for missing keys."""
    try:
        c = _conn()
        rows = c.execute("SELECT key, value FROM app_settings").fetchall()
        d = {r["key"]: r["value"] for r in rows}
    except Exception:
        d = {}

    # Return with defaults for missing keys
    return {
        "clinic_name": d.get("clinic_name", "Bharat AI OPD"),
        "clinic_address": d.get("clinic_address", ""),
        "doc_name": d.get("doc_name", "Dr. Doctor"),
        "doc_degree": d.get("doc_degree", "MBBS"),
        "doc_subtitle": d.get("doc_subtitle", "General Physician"),
        "doc_reg_no": d.get("doc_reg_no", ""),
        "doc_phone": d.get("doc_phone", ""),
        "doc_email": d.get("doc_email", ""),
        "doc_extra_quals": d.get("doc_extra_quals", ""),
        "groq_api_key": d.get("groq_api_key", ""),
        "supabase_url": d.get("supabase_url", ""),
        "supabase_key": d.get("supabase_key", ""),
        "google_sheet_webhook": d.get("google_sheet_webhook", ""),
    }


def save_settings(key_value_dict: dict):
    """Save multiple settings at once. Accepts dict of key:value pairs."""
    try:
        c = _conn()
        for k, v in key_value_dict.items():
            c.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (k, str(v)))
        c.commit()
        log.info("Settings saved: %s", list(key_value_dict.keys()))
    except Exception as e:
        log.error("save_settings error: %s", e)


# ── Patient CRUD ────────────────────────────────────────────────────────────
def save_patient(patient_name, phone, vitals, fee, complaints, medicines, investigations, specialty, doctor_id="chief"):
    """Save a new patient record to database. Also pushes to Google Sheet webhook if configured."""
    try:
        c = _conn()
        c.execute(
            "INSERT INTO patients (doctor_id, patient_name, phone, vitals, fee, complaints, "
            "medicines, investigations, specialty, date) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (doctor_id, patient_name, phone, vitals, fee, complaints, medicines,
             investigations, specialty, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        c.commit()

        # Save drug names for autocomplete
        import re
        drug_matches = re.findall(r'(?:Tab\.|Cap\.|Syp\.|Inj\.|Gel\.|Drops|Spray|Inhaler|Patch|Cream)\s*([A-Za-z][\w\s-]+?)(?:\s+[\d]|$)', medicines)
        for dm in drug_matches:
            dm = dm.strip()
            if dm and len(dm) >= 3:
                c.execute("INSERT OR IGNORE INTO drug_history (doctor_id, drug_name) VALUES (?, ?)",
                          (doctor_id, dm.strip()))

        c.commit()

        # Push to Google Sheet webhook if configured
        try:
            import requests
            webhook = get_settings().get("google_sheet_webhook", "")
            if webhook and webhook.startswith("http"):
                payload = {
                    "patient_name": patient_name, "phone": phone, "vitals": vitals,
                    "fee": str(fee), "complaints": complaints[:100] if complaints else "",
                    "medicines": medicines[:200] if medicines else "",
                    "specialty": specialty, "date": datetime.now().strftime("%Y-%m-%d"),
                    "doctor_id": doctor_id,
                }
                requests.post(webhook, json=payload, timeout=10)
        except Exception:
            pass

        log.info("Patient saved: %s (%s)", patient_name, doctor_id)
        return True
    except Exception as e:
        log.error("save_patient error: %s", e)
        return False


def search_patients(query, doctor_id="chief"):
    """Search patients by name or phone. Returns list of dicts."""
    try:
        c = _conn()
        rows = c.execute(
            "SELECT * FROM patients WHERE doctor_id=? AND (patient_name LIKE ? OR phone LIKE ?) "
            "ORDER BY date DESC LIMIT 50",
            (doctor_id, f"%{query}%", f"%{query}%")
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("search_patients error: %s", e)
        return []


def get_patients_filter(date_filter: str, doctor_id="chief"):
    """Get patients filtered by date range. date_filter: Today, Yesterday, Last 5 Days, All Time."""
    try:
        c = _conn()
        today = date.today()
        if date_filter == "Today":
            rows = c.execute(
                "SELECT * FROM patients WHERE doctor_id=? AND date(date)=? ORDER BY date DESC",
                (doctor_id, today.isoformat())
            ).fetchall()
        elif date_filter == "Yesterday":
            yday = (today - timedelta(days=1)).isoformat()
            rows = c.execute(
                "SELECT * FROM patients WHERE doctor_id=? AND date(date)=? ORDER BY date DESC",
                (doctor_id, yday)
            ).fetchall()
        elif date_filter == "Last 5 Days":
            five = (today - timedelta(days=5)).isoformat()
            rows = c.execute(
                "SELECT * FROM patients WHERE doctor_id=? AND date(date)>=? ORDER BY date DESC",
                (doctor_id, five)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM patients WHERE doctor_id=? ORDER BY date DESC LIMIT 500",
                (doctor_id,)
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("get_patients_filter error: %s", e)
        return []


def get_all_patients_admin(doctor_id):
    """Get ALL patients for admin view (no date limit)."""
    try:
        c = _conn()
        rows = c.execute(
            "SELECT * FROM patients WHERE doctor_id=? ORDER BY date DESC",
            (doctor_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("get_all_patients_admin error: %s", e)
        return []


# ── Drug Suggestions (autocomplete) ────────────────────────────────────────
def get_drug_suggestions(query, doctor_id="chief"):
    """Get previously used drug names matching query (autocomplete)."""
    try:
        c = _conn()
        rows = c.execute(
            "SELECT DISTINCT drug_name FROM drug_history WHERE doctor_id=? AND drug_name LIKE ? "
            "ORDER BY date DESC LIMIT 8",
            (doctor_id, f"%{query}%")
        ).fetchall()
        return [r["drug_name"] for r in rows]
    except Exception as e:
        log.error("get_drug_suggestions error: %s", e)
        return []


# ── Templates ───────────────────────────────────────────────────────────────
def get_templates(category="Rx"):
    """Get all templates for a category. Returns dict {name: content}."""
    try:
        c = _conn()
        rows = c.execute(
            "SELECT name, content FROM templates WHERE category=? ORDER BY name",
            (category,)
        ).fetchall()
        return {r["name"]: r["content"] for r in rows}
    except Exception as e:
        log.error("get_templates error: %s", e)
        return {}


def save_template(category, name, content):
    """Save or update a template."""
    try:
        c = _conn()
        c.execute(
            "INSERT OR REPLACE INTO templates (category, name, content) VALUES (?, ?, ?)",
            (category, name, content)
        )
        c.commit()
        return True
    except Exception as e:
        log.error("save_template error: %s", e)
        return False


def delete_template(name):
    """Delete a template by name."""
    try:
        c = _conn()
        c.execute("DELETE FROM templates WHERE name=?", (name,))
        c.commit()
        return True
    except Exception as e:
        log.error("delete_template error: %s", e)
        return False


# ── Specialty Upgrades & Starred ────────────────────────────────────────────
def save_upgrade(patient_name, vitals, original_rx, specialty, upgraded_rx, evidence=""):
    """Save a specialty upgrade record. Returns the record ID."""
    try:
        c = _conn()
        cur = c.execute(
            "INSERT INTO specialty_upgrades (patient_name, vitals, original_rx, specialty, "
            "upgraded_rx, evidence) VALUES (?, ?, ?, ?, ?, ?)",
            (patient_name, vitals, original_rx, specialty, upgraded_rx, evidence)
        )
        c.commit()
        rid = cur.lastrowid
        return rid
    except Exception as e:
        log.error("save_upgrade error: %s", e)
        return 0


def star_upgrade(upgrade_id, star_note=""):
    """Mark a specialty upgrade as starred."""
    try:
        c = _conn()
        c.execute(
            "UPDATE specialty_upgrades SET starred=1, star_note=? WHERE id=?",
            (star_note, upgrade_id)
        )
        c.commit()
        return True
    except Exception as e:
        log.error("star_upgrade error: %s", e)
        return False


def get_starred():
    """Get all starred specialty comparisons."""
    try:
        c = _conn()
        rows = c.execute(
            "SELECT * FROM specialty_upgrades WHERE starred=1 ORDER BY date DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("get_starred error: %s", e)
        return []


# ── Pending Rx (Batch Scan) ────────────────────────────────────────────────
def save_pending(doctor_id, image_b64, ai_extracted, patient_name, phone, vitals,
                 fee, complaints, medicines, investigations):
    """Save a pending batch-scan prescription."""
    try:
        c = _conn()
        c.execute(
            "INSERT INTO pending_rx (doctor_id, image_b64, ai_extracted, patient_name, phone, "
            "vitals, fee, complaints, medicines, investigations) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (doctor_id, image_b64, ai_extracted, patient_name, phone, vitals,
             fee, complaints, medicines, investigations)
        )
        c.commit()
        return True
    except Exception as e:
        log.error("save_pending error: %s", e)
        return False


def get_pending(doctor_id="chief"):
    """Get all pending prescriptions for review."""
    try:
        c = _conn()
        rows = c.execute(
            "SELECT * FROM pending_rx WHERE doctor_id=? AND status='pending' ORDER BY uploaded_at DESC",
            (doctor_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("get_pending error: %s", e)
        return []


def update_pending(rx_id, patient_name, phone, vitals, fee, complaints, medicines, investigations, status):
    """Update a pending prescription (edit fields or change status)."""
    try:
        c = _conn()
        c.execute(
            "UPDATE pending_rx SET patient_name=?, phone=?, vitals=?, fee=?, complaints=?, "
            "medicines=?, investigations=?, status=? WHERE id=?",
            (patient_name, phone, vitals, fee, complaints, medicines, investigations, status, rx_id)
        )
        c.commit()
        return True
    except Exception as e:
        log.error("update_pending error: %s", e)
        return False


def finalize_pending(rx_id, doctor_id, patient_name, phone, vitals, fee, complaints, medicines, investigations):
    """Approve a pending Rx — save to patients table and mark as approved."""
    try:
        update_pending(rx_id, patient_name, phone, vitals, fee, complaints, medicines, investigations, "approved")
        save_patient(patient_name, phone, vitals, fee, complaints, medicines, investigations, "General Physician", doctor_id)
        return True
    except Exception as e:
        log.error("finalize_pending error: %s", e)
        return False


def count_pending(doctor_id="chief"):
    """Count pending prescriptions for badge notification."""
    try:
        c = _conn()
        row = c.execute(
            "SELECT COUNT(*) as cnt FROM pending_rx WHERE doctor_id=? AND status='pending'",
            (doctor_id,)
        ).fetchone()
        return row["cnt"] if row else 0
    except Exception as e:
        log.error("count_pending error: %s", e)
        return 0


# ── Licenses ────────────────────────────────────────────────────────────────
def create_license(doctor_id, doctor_name, doctor_email, doctor_phone, pin,
                   clinic_name, specialty, expiry_date, notes=""):
    """Create a new doctor license. Returns True/False."""
    try:
        c = _conn()
        c.execute(
            "INSERT INTO licenses (doctor_id, doctor_name, doctor_email, doctor_phone, pin, "
            "clinic_name, specialty, expiry_date, notes) VALUES (?,?,?,?,?,?,?,?,?)",
            (doctor_id, doctor_name, doctor_email or "", doctor_phone or "", pin,
             clinic_name or "", specialty or "", str(expiry_date), notes or "")
        )
        c.commit()
        log.info("License created: %s (%s)", doctor_name, doctor_id)
        return True
    except Exception as e:
        log.error("create_license error: %s", e)
        return False


def get_all_licenses():
    """Get all doctor licenses."""
    try:
        c = _conn()
        rows = c.execute("SELECT * FROM licenses ORDER BY created_date DESC").fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error("get_all_licenses error: %s", e)
        return []


def delete_license(license_id):
    """Delete a license by ID."""
    try:
        c = _conn()
        c.execute("DELETE FROM licenses WHERE id=?", (license_id,))
        c.commit()
        return True
    except Exception as e:
        log.error("delete_license error: %s", e)
        return False


def verify_login_pin(pin, role_override=None):
    """
    Verify login PIN. Returns dict with: role, doctor_id, doctor_name, clinic_name
    Returns None if PIN doesn't match any role or license.
    """
    pin = pin.strip()

    # Check built-in roles first (chief, junior, admin)
    for role, stored_pin in PINS.items():
        if pin == stored_pin:
            if role == "admin":
                return {"role": "admin", "doctor_id": "admin", "doctor_name": "Administrator", "clinic_name": "Bharat AI OPD"}
            else:
                return {"role": role, "doctor_id": role, "doctor_name": "Chief Doctor" if role == "chief" else "Junior Doctor", "clinic_name": get_settings().get("clinic_name", "Bharat AI OPD")}

    # Check license PINs
    try:
        c = _conn()
        row = c.execute("SELECT * FROM licenses WHERE pin=?", (pin,)).fetchone()
        if row:
            d = dict(row)
            # Check expiry
            try:
                exp = date.fromisoformat(str(d["expiry_date"])[:10])
                if exp < date.today():
                    return None  # Expired
            except Exception:
                pass
            return {
                "role": "licensed",
                "doctor_id": d["doctor_id"],
                "doctor_name": d["doctor_name"],
                "clinic_name": d["clinic_name"] or get_settings().get("clinic_name", "Bharat AI OPD"),
                "specialty": d.get("specialty", ""),
            }
    except Exception as e:
        log.error("verify_login_pin license check error: %s", e)

    return None


# ── Data Import ─────────────────────────────────────────────────────────────
def import_rows(rows, doctor_id="chief"):
    """Import multiple patient records from a list of dicts. Returns count imported."""
    imported = 0
    for row in rows:
        try:
            save_patient(
                patient_name=row.get("patient_name", row.get("name", "")),
                phone=str(row.get("phone", "")),
                vitals=row.get("vitals", ""),
                fee=str(row.get("fee", "300")),
                complaints=row.get("complaints", ""),
                medicines=row.get("medicines", row.get("prescription", row.get("rx", ""))),
                investigations=row.get("investigations", ""),
                specialty=row.get("specialty", "General Physician"),
                doctor_id=doctor_id,
            )
            imported += 1
        except Exception as e:
            log.error("import_rows error for row: %s", e)
    log.info("Imported %d rows for %s", imported, doctor_id)
    return imported


# ── Patient count for admin stats ───────────────────────────────────────────
def count_patients(doctor_id=""):
    """Count total patients. Optional doctor_id filter."""
    try:
        c = _conn()
        if doctor_id:
            row = c.execute("SELECT COUNT(*) as cnt FROM patients WHERE doctor_id=?", (doctor_id,)).fetchone()
        else:
            row = c.execute("SELECT COUNT(*) as cnt FROM patients").fetchone()
        return row["cnt"] if row else 0
    except Exception:
        return 0
