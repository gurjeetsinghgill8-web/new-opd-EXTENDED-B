"""
Bharat AI OPD App — Central Configuration
Saari clinic settings, API keys, feature flags yahi se aati hain.
"""

# ── Security PINs ────────────────────────────────────────────────────────────
PINS: dict[str, str] = {
    "chief": "5555",
    "junior": "1234",
    "admin": "9999",
}

# ── Clinic Identity ──────────────────────────────────────────────────────────
CLINIC_NAME: str = "Bharat AI OPD"
CLINIC_ADDRESS: str = "123, Main Road, New Delhi – 110001"
CLINIC_PHONE: str = "+91-9876543210"
CLINIC_EMAIL: str = "admin@bharatopd.in"

# ── External Services ────────────────────────────────────────────────────────
SUPABASE_URL: str = ""
SUPABASE_KEY: str = ""
GROQ_API_KEY: str = ""
GOOGLE_SHEET_ID: str = ""

# ── Feature Flags (saari features on/off yahi se control hoti hain) ──────────
FEATURE_FLAGS: dict[str, bool] = {
    "voice_scribe": True,
    "ai_rx": True,
    "pdf_letterhead": True,
    "specialty_upgrade": True,
    "cme_generator": True,
    "research_agent": True,
    "waiting_room": True,
    "vitals_banner": True,
}

# ── Compliance / Regulatory Limits ───────────────────────────────────────────
COMPLIANCE: dict[str, int | bool] = {
    "max_rx_per_day": 50,
    "drug_lookup_required": True,
    "consent_required": True,
    "data_retention_days": 365,
}

# ── Supported Specialties ────────────────────────────────────────────────────
SPECIALTIES: list[str] = [
    "General Medicine", "Cardiology", "Dermatology", "ENT",
    "Gastroenterology", "Neurology", "Orthopedics", "Pediatrics",
    "Psychiatry", "Pulmonology", "Ophthalmology", "Gynecology",
    "Urology", "Endocrinology", "Rheumatology",
]

# ── Database Path (SQLite file) ──────────────────────────────────────────────
DB_PATH: str = "opd_data.db"
