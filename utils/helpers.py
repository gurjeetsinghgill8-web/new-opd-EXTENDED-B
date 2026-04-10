"""helpers — Bharat AI OPD: fee parsing, vitals, drugs, progress, currency."""
import logging, re
from typing import Any, Dict, List
import streamlit as st

logger = logging.getLogger(__name__)
_VP = {
    "bp": re.compile(r"BP\s*[:=]?\s*(\d+)\s*/\s*(\d+)", re.I),
    "pulse": re.compile(r"Pulse\s*[:=]?\s*(\d+)", re.I),
    "temp": re.compile(r"Temp\s*[:=]?\s*([\d.]+)\s*[°]?\s*[FfCc]", re.I),
    "spo2": re.compile(r"SpO2?\s*[:=]?\s*(\d+)", re.I),
    "weight": re.compile(r"Weight\s*[:=]?\s*([\d.]+)\s*kg", re.I),
}


def clean_fee_string(fee_str: str) -> float:
    """Fee string → float. 'Free', 'N/A', invalid → 0.0."""
    try:
        if not fee_str or not isinstance(fee_str, str):
            return 0.0
        s = fee_str.strip()
        if re.search(r"(free|n/?a|none|nil|–|-)", s, re.I):
            return 0.0
        return float(re.sub(r"[₹,\s]", "", s))
    except (ValueError, TypeError):
        return 0.0


def parse_vitals_string(vitals_str: str) -> Dict[str, Any]:
    """Vitals string → dict: bp_systolic, bp_diastolic, bp, pulse, temp_celsius, spo2, weight_kg."""
    r: Dict[str, Any] = {}
    if not vitals_str or not isinstance(vitals_str, str):
        return r
    try:
        m = _VP["bp"].search(vitals_str)
        if m:
            r["bp_systolic"], r["bp_diastolic"] = int(m.group(1)), int(m.group(2))
            r["bp"] = f"{m.group(1)}/{m.group(2)}"
        m = _VP["pulse"].search(vitals_str)
        if m:
            r["pulse"] = int(m.group(1))
        m = _VP["temp"].search(vitals_str)
        if m:
            r["temp_original"] = float(m.group(1))
            r["temp_celsius"] = round((r["temp_original"] - 32) * 5 / 9, 1)
        m = _VP["spo2"].search(vitals_str)
        if m:
            r["spo2"] = int(m.group(1))
        m = _VP["weight"].search(vitals_str)
        if m:
            r["weight_kg"] = float(m.group(1))
    except (ValueError, AttributeError) as e:
        logger.error("Vitals parse error: %s", e)
    return r


def extract_drugs_from_rx(rx_text: str) -> List[str]:
    """Rx text se drug names nikalo — Capitalized word + dosage (mg/ml/mcg)."""
    if not rx_text or not isinstance(rx_text, str):
        return []
    try:
        pat = re.compile(
            r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})"
            r"\s+\d+(?:\.\d+)?\s*(?:mg|ml|mcg|μg|IU|mg/ml|%)\b", re.I)
        seen, unique = set(), []
        for d in pat.findall(rx_text):
            low = d.strip().lower()
            if low not in seen and len(low) > 2:
                seen.add(low); unique.append(d.strip())
        return unique
    except Exception as e:
        logger.error("Drug extraction error: %s", e); return []


def compare_progress(old_vitals: str, new_vitals: str) -> Dict[str, List[str]]:
    """Do vitals compare karo → {improved, worsened, stable} lists."""
    res: Dict[str, List[str]] = {"improved": [], "worsened": [], "stable": []}
    o, n = parse_vitals_string(old_vitals), parse_vitals_string(new_vitals)
    try:
        if "bp" in o and "bp" in n:
            tag = ("Improved" if n["bp_systolic"] < o["bp_systolic"] and n["bp_diastolic"] < o["bp_diastolic"]
                   else "Worsened" if n["bp_systolic"] > o["bp_systolic"] or n["bp_diastolic"] > o["bp_diastolic"] else "Stable")
            res[tag.lower()].append(f"BP: {o['bp']} → {n['bp']} ({tag})")
        for key, unit, higher_good in [("pulse","",False),("spo2","%",True),("temp_celsius","°C",False)]:
            if key in o and key in n:
                if higher_good:
                    tag = "Improved" if n[key] > o[key] else ("Worsened" if n[key] < o[key] else "Stable")
                else:
                    tag = "Improved" if n[key] < o[key] else ("Worsened" if n[key] > o[key] else "Stable")
                lbl = key.replace("temp_celsius","Temp").replace("spo2","SpO2").replace("pulse","Pulse")
                res[tag.lower()].append(f"{lbl}: {o[key]}{unit} → {n[key]}{unit} ({tag})")
    except (KeyError, TypeError) as e:
        logger.error("Progress compare error: %s", e)
    return res


def safe_session_set(key: str, value: Any) -> None:
    """Streamlit session_state mein safely value set karo."""
    try:
        st.session_state[key] = value
    except Exception as e:
        logger.error("Session state error for '%s': %s", key, e)


def format_hinglish_currency(amount: float) -> str:
    """Indian lakh-system formatting: 100000 → ₹1,00,000."""
    try:
        rounded = int(round(amount)); sign = "-" if rounded < 0 else ""; rounded = abs(rounded)
        if rounded == 0: return "₹0"
        s = str(rounded)
        if len(s) <= 3: return f"₹{sign}{s}"
        out, rem = s[-3:], s[:-3]
        while rem: out = rem[-2:] + "," + out; rem = rem[:-2]
        return f"₹{sign}{out}"
    except (ValueError, TypeError) as e:
        logger.error("Currency format error (%s): %s", amount, e); return f"₹{amount}"
