"""SQLite Client — Bharat OPD local database. Helper functions se boilerplate kam kiya hai."""
import logging, sqlite3
from datetime import datetime
from config import settings

log = logging.getLogger(__name__)

_SCHEMA = """CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, age TEXT, gender TEXT, phone TEXT,
    address TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS prescriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, doctor TEXT, date TEXT,
    complaints TEXT, findings TEXT, vitals TEXT, drugs TEXT, investigations TEXT,
    advice TEXT, follow_up TEXT, specialty TEXT, pdf_path TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS drugs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, category TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, content TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT, license_key TEXT UNIQUE, doctor_name TEXT,
    expiry_date TEXT, role TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT);"""
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH); conn.row_factory = sqlite3.Row; return conn

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def _fetch(sql: str, params=()) -> list[dict]:
    try:
        c = get_connection(); rows = c.execute(sql, params).fetchall(); c.close()
        return [dict(r) for r in rows]
    except Exception as e: log.error("DB fetch: %s", e); return []

def _fetchone(sql: str, params=()) -> dict | None:
    try:
        c = get_connection(); row = c.execute(sql, params).fetchone(); c.close()
        return dict(row) if row else None
    except Exception as e: log.error("DB fetchone: %s", e); return None

def _exec(sql: str, params=()) -> bool:
    try:
        c = get_connection(); c.execute(sql, params); c.commit(); c.close(); return True
    except Exception as e: log.error("DB exec: %s", e); return False

def init_db() -> None:
    try:
        c = get_connection(); c.executescript(_SCHEMA); c.close()
        log.info("SQLite tables initialised.")
    except Exception as e: log.error("init_db: %s", e)

def insert_patient(d: dict) -> int:
    try:
        c = get_connection()
        cur = c.execute(
            "INSERT INTO patients (name,age,gender,phone,address,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            (d.get("name",""), d.get("age",""), d.get("gender",""), d.get("phone",""), d.get("address",""), _now(), _now()))
        c.commit(); pid = cur.lastrowid; c.close(); return pid or 0
    except Exception as e: log.error("insert_patient: %s", e); return 0

def search_patients(q: str) -> list[dict]:
    return _fetch("SELECT * FROM patients WHERE name LIKE ? OR phone LIKE ? ORDER BY id DESC", (f"%{q}%", f"%{q}%"))

def get_patient_by_id(pid: int) -> dict | None:
    return _fetchone("SELECT * FROM patients WHERE id=?", (pid,))

def update_patient(pid: int, d: dict) -> bool:
    return _exec("UPDATE patients SET name=?,age=?,gender=?,phone=?,address=?,updated_at=? WHERE id=?",
        (d.get("name",""), d.get("age",""), d.get("gender",""), d.get("phone",""), d.get("address",""), _now(), pid))

def insert_rx(d: dict) -> int:
    try:
        c = get_connection()
        cur = c.execute(
            "INSERT INTO prescriptions (patient_id,doctor,date,complaints,findings,vitals,drugs,"
            "investigations,advice,follow_up,specialty,pdf_path,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (d.get("patient_id",0), d.get("doctor",""), d.get("date",""), d.get("complaints",""),
             d.get("findings",""), d.get("vitals",""), d.get("drugs",""), d.get("investigations",""),
             d.get("advice",""), d.get("follow_up",""), d.get("specialty",""), d.get("pdf_path",""), _now()))
        c.commit(); rid = cur.lastrowid; c.close(); return rid or 0
    except Exception as e: log.error("insert_rx: %s", e); return 0

def get_rx_by_patient(pid: int) -> list[dict]:
    return _fetch("SELECT * FROM prescriptions WHERE patient_id=? ORDER BY id DESC", (pid,))

def insert_drug(name: str, cat: str) -> bool:
    return _exec("INSERT OR IGNORE INTO drugs (name,category,created_at) VALUES (?,?,?)", (name, cat, _now()))

def search_drugs(q: str) -> list[dict]:
    return _fetch("SELECT * FROM drugs WHERE name LIKE ? ORDER BY name", (f"%{q}%",))

def get_all_drugs() -> list[dict]:
    return _fetch("SELECT * FROM drugs ORDER BY name")

def save_template(name: str, content: str) -> bool:
    return _exec("INSERT OR REPLACE INTO templates (name,content,created_at) VALUES (?,?,?)", (name, content, _now()))

def get_templates() -> list[dict]:
    return _fetch("SELECT * FROM templates ORDER BY id DESC")

def save_license(key: str, doc: str, exp: str) -> bool:
    return _exec("INSERT OR REPLACE INTO licenses (license_key,doctor_name,expiry_date,role,created_at) VALUES (?,?,?,?,?)",
        (key, doc, exp, "doctor", _now()))

def get_licenses() -> list[dict]:
    return _fetch("SELECT * FROM licenses ORDER BY id DESC")

def delete_license(key: str) -> bool:
    return _exec("DELETE FROM licenses WHERE license_key=?", (key,))

def get_settings() -> dict:
    rows = _fetch("SELECT key,value FROM app_settings")
    return {r["key"]: r["value"] for r in rows}

def save_settings(data: dict) -> bool:
    try:
        c = get_connection()
        for k, v in data.items():
            c.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES (?,?)", (k, str(v)))
        c.commit(); c.close(); return True
    except Exception as e: log.error("save_settings: %s", e); return False
