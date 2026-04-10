"""
Bharat AI OPD App — Central Configuration
Saari clinic settings, API keys, feature flags, specialties yahi se aati hain.
"""

import os

# ── Security PINs ────────────────────────────────────────────────────────────
PINS: dict = {
    "chief": "5555",
    "junior": "1234",
    "admin": "9999",
}

# ── Clinic Identity (defaults — Settings page se override hota hai) ──────────
CLINIC_NAME: str = "Bharat AI OPD"
CLINIC_ADDRESS: str = "123, Main Road, New Delhi - 110001"
CLINIC_PHONE: str = ""
CLINIC_EMAIL: str = ""

# ── External Services (Streamlit Secrets ya env vars se aate hain) ────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
GOOGLE_SHEET_ID: str = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_SHEET_WEBHOOK: str = os.getenv("GOOGLE_SHEET_WEBHOOK", "")

# ── Supported Specialties (dict with persona, guidelines, focus) ─────────────
SPECIALTIES: dict = {
    "Cardiology": {
        "persona": "Senior Interventional Cardiologist with 20+ years experience in Indian OPD settings",
        "guidelines": "ACC/AHA 2023 Guidelines, Indian Cardiology Society protocols, NHB guidelines",
        "focus": "Hypertension, Ischemic Heart Disease, Heart Failure, Arrhythmias, Dyslipidemia"
    },
    "Endocrinology": {
        "persona": "Senior Endocrinologist specializing in Diabetes and Thyroid disorders",
        "guidelines": "RSSDI 2023 Guidelines, ADA Standards of Care, Indian Thyroid Society protocols",
        "focus": "Type 2 DM, Thyroid disorders, PCOS, Osteoporosis, Adrenal disorders"
    },
    "Neurology": {
        "persona": "Senior Neurologist with expertise in stroke and headache management",
        "guidelines": "American Academy of Neurology guidelines, Indian Stroke Association protocols",
        "focus": "Stroke, Epilepsy, Headache/Migraine, Parkinson's, Neuropathy"
    },
    "Gastroenterology": {
        "persona": "Senior Gastroenterologist experienced in Indian GI disorders",
        "guidelines": "APDW guidelines, Indian Society of Gastroenterology protocols",
        "focus": "Acid Peptic Disease, IBS, Liver disorders, Pancreatitis, GI infections"
    },
    "Orthopedics": {
        "persona": "Senior Orthopedic Surgeon specializing in conservative management",
        "guidelines": "AAOS guidelines, IOA protocols for Indian population",
        "focus": "Back pain, Arthritis, Fractures, Sports injuries, Joint pain"
    },
    "Dermatology": {
        "persona": "Senior Dermatologist with expertise in tropical and Indian skin conditions",
        "guidelines": "IADVL guidelines, Indian dermatology practice protocols",
        "focus": "Eczema, Psoriasis, Fungal infections, Acne, Pigmentation disorders"
    },
    "Pulmonology": {
        "persona": "Senior Pulmonologist specializing in COPD and asthma management",
        "guidelines": "GOLD 2024 guidelines, GINA asthma guidelines, Indian Chest Society protocols",
        "focus": "COPD, Asthma, TB, Pneumonia, Respiratory infections"
    },
    "Pediatrics": {
        "persona": "Senior Pediatrician with 20+ years in Indian pediatric OPD",
        "guidelines": "IAP protocols, WHO IMCI guidelines, Indian immunization schedule",
        "focus": "Childhood infections, Growth monitoring, Vaccinations, Nutritional disorders"
    },
    "Psychiatry": {
        "persona": "Senior Psychiatrist experienced in Indian mental health landscape",
        "guidelines": "Indian Psychiatric Society guidelines, WHO mental health protocols",
        "focus": "Depression, Anxiety, Insomnia, OCD, Stress disorders"
    },
}

# ── Drug Entry Helpers ───────────────────────────────────────────────────────
DRUG_TYPES: list = ["Tab.", "Cap.", "Syp.", "Inj.", "Gel.", "Drops", "Spray", "Inhaler", "Patch", "Cream"]
DRUG_FREQUENCIES: list = ["OD (Once daily)", "BD (Twice daily)", "TDS (Three times)", "QID (Four times)",
                           "SOS (As needed)", "HS (At bedtime)", "STAT (Immediately)", "Weekly", "Monthly"]
DRUG_TIMINGS: list = ["After Breakfast", "After Lunch", "After Dinner", "Before Breakfast",
                      "Before Lunch", "Before Dinner", "With Food", "Empty Stomach", "Any Time"]

# ── Quick Investigations (one-click buttons) ─────────────────────────────────
QUICK_INVESTIGATIONS: list = [
    "CBC", "ESR", "FBS", "PPBS", "HbA1c", "RBS", "Lipid Profile", "RFT",
    "LFT", "ECG", "X-Ray Chest PA", "USG Abdomen", "Urine R/M",
    "TSH", "Vitamin D", "Vitamin B12", "CRP", "Procalcitonin",
]

# ── Feature Flags ────────────────────────────────────────────────────────────
FEATURE_FLAGS: dict = {
    "voice_scribe": True,
    "ai_rx": True,
    "pdf_letterhead": True,
    "specialty_upgrade": True,
    "cme_generator": True,
    "research_agent": True,
    "waiting_room": True,
    "vitals_banner": True,
    "batch_scan": True,
}

# ── Compliance ───────────────────────────────────────────────────────────────
COMPLIANCE: dict = {
    "max_rx_per_day": 100,
    "drug_lookup_required": True,
    "consent_required": True,
    "data_retention_days": 365,
}

# ── Database ─────────────────────────────────────────────────────────────────
DB_PATH: str = "opd_data.db"

# ── Groq AI Model ────────────────────────────────────────────────────────────
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
VISION_MODEL: str = os.getenv("VISION_MODEL", "llama-3.2-11b-vision-preview")
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "whisper-large-v3")
