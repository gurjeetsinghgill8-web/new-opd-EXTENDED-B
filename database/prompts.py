"""prompts — Bharat AI OPD: system prompts aur Rx output validator."""
import logging, re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)
_REQUIRED_RX_SECTIONS: List[str] = ["Diagnosis", "Drugs", "Advice", "Follow-up"]


def get_rx_prompt(patient_data: Dict[str, Any]) -> str:
    """GP prescription system prompt — Indian clinical context ke saath."""
    cd = patient_data.get("current_drugs", "None")
    return (
        "You are an experienced Indian General Practitioner AI assistant.\n"
        "Generate a structured clinical prescription in plain text (no markdown) for:\n\n"
        f"Patient: {patient_data.get('name','Unknown')}, {patient_data.get('age','N/A')} yrs, "
        f"{patient_data.get('gender','N/A')}\n"
        f"Chief Complaints: {patient_data.get('complaints','Not provided')}\n"
        f"Vitals: {patient_data.get('vitals','Not provided')}\n"
        f"Current Medications: {cd}\n\n"
        "IMPORTANT (Indian context):\n"
        "1. Use INN/generic drug names with Indian standard dosages (mg/mL).\n"
        "2. Mention brand alternatives in brackets where relevant.\n"
        "3. Specify form (tab/cap/syp/inj), frequency, duration, food timing.\n"
        "4. Suggest investigations if needed (blood tests, X-ray, etc.).\n"
        "5. Clear follow-up timeline (3 days, 1 week, etc.).\n"
        "6. Add lifestyle/diet advice in simple language.\n"
        "7. Flag red-flag symptoms requiring urgent referral.\n\n"
        "OUTPUT FORMAT (exact headings):\nDiagnosis:\nDrugs:\nAdvice:\nFollow-up:"
    )


def get_specialty_upgrade_prompt(complaints: str, current_specialty: str) -> str:
    """Specialist referral prompt — JSON output: specialty, urgency, reasoning."""
    return (
        "You are a senior Indian doctor advising on specialist referral.\n\n"
        f"Patient Complaints: {complaints}\nCurrent Department: {current_specialty}\n\n"
        "Analyze if this patient needs referral. Respond ONLY with valid JSON:\n"
        '{"recommended_specialty": "<name or No referral needed>", '
        '"urgency": "<routine|urgent|emergency>", '
        '"reasoning": "<brief clinical reasoning>", '
        '"investigations_needed": ["<list>"], '
        '"interim_management": "<what to do while waiting>"}'
    )


def get_cme_prompt(topic: str) -> str:
    """CME guideline summary prompt — Indian guidelines (NHB, ICMR, API) included."""
    return (
        "You are a medical educator creating a CME summary.\n\n"
        f"Topic: {topic}\n\n"
        "Create a concise CME summary:\n"
        "1. Definitions and epidemiology (India-specific data preferred).\n"
        "2. Diagnostic criteria (Indian guidelines: NHB, ICMR, API, NICE adapted).\n"
        "3. Stepwise management for Indian OPD settings.\n"
        "4. Red flags and specialist referral triggers.\n"
        "5. Recent advances (last 2 years) for Indian practice.\n"
        "6. 3-5 take-home points.\n"
        "Plain text only. No markdown."
    )


def get_research_prompt(question: str) -> str:
    """Research query prompt — literature review with evidence levels."""
    return (
        "You are a medical research assistant providing evidence-based answers.\n\n"
        f"Research Question: {question}\n\n"
        "Provide a structured literature review:\n"
        "1. Summary of current evidence (cite landmark studies).\n"
        "2. Evidence level per recommendation (Level I-V).\n"
        "3. Key trials with results (NNT, RR, OR where available).\n"
        "4. Indian context — India-specific studies or guidelines.\n"
        "5. Knowledge gaps and ongoing research.\n"
        "6. Clinical bottom line for Indian physicians.\n"
        "Plain text only. No markdown."
    )


def validate_rx_output(text: str) -> Dict[str, Any]:
    """AI Rx output validate karo — check required sections. Return valid/sections/missing."""
    try:
        found, missing = [], []
        for section in _REQUIRED_RX_SECTIONS:
            if re.search(rf"\b{re.escape(section)}\s*:?", text, re.IGNORECASE):
                found.append(section)
            else:
                missing.append(section)
        return {"valid": len(missing) == 0, "sections": found, "missing": missing}
    except Exception as e:
        logger.error("Rx validation error: %s", e)
        return {"valid": False, "sections": [], "missing": list(_REQUIRED_RX_SECTIONS)}
