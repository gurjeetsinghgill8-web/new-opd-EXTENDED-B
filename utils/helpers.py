"""
helpers — Common utility functions used across all modules.
Fee parsing, vitals extraction, comparison, CSV generation, etc.
"""

import re
import io
from typing import Dict, Any, List, Optional


def clean_fee(f) -> int:
    """Extract integer fee value from string."""
    n = re.findall(r'\d+', str(f))
    return int(n[0]) if n else 0


def safe_str(t) -> str:
    """Convert to string, replacing non-latin-1 chars for PDF compatibility."""
    return str(t).encode('latin-1', 'replace').decode('latin-1')


def extract_vitals_dict(vitals_str: str) -> Dict[str, Any]:
    """
    Extract structured vitals from text string.
    Returns dict with keys: sys, dia, sugar, weight, hr, spo2, temp
    Parses formats like: BP 130/80, RBS 140, Wt 70kg, HR 72, SpO2 98%, Temp 98.6F
    """
    v = str(vitals_str).lower()
    result = {}

    # BP: "130/80" or "BP 130/80" or "BP: 130/80"
    bp = re.search(r'(\d{2,3})\s*/\s*(\d{2,3})', v)
    if bp:
        result["sys"] = int(bp.group(1))
        result["dia"] = int(bp.group(2))

    # Sugar: "RBS 140" or "FBS 110" or "Sugar: 180" or "BS 200"
    sg = re.search(r'(?:rbs|fbs|pp\s*bs|ppbs|sugar|bs|glucose)\s*[:=]?\s*(\d{2,4})', v)
    if sg:
        result["sugar"] = int(sg.group(1))

    # Weight: "Wt 70" or "Weight 70" or "70kg"
    wt = re.search(r'(?:wt|weight)\s*[:=]?\s*(\d{2,3})', v)
    if wt:
        result["weight"] = int(wt.group(1))

    # Heart Rate: "HR 72" or "Pulse 72" or "PR 72"
    hr = re.search(r'(?:hr|pulse|pr)\s*[:=]?\s*(\d{2,3})', v)
    if hr:
        result["hr"] = int(hr.group(1))

    # SpO2: "SpO2 98" or "SPO2 98%"
    spo2 = re.search(r'spo2?\s*[:=]?\s*(\d{2,3})', v)
    if spo2:
        result["spo2"] = int(spo2.group(1))

    # Temperature: "Temp 98.6" or "98.6F" or "Temperature 37C"
    temp = re.search(r'(?:temp|temperature)\s*[:=]?\s*(\d{2,3}\.?\d*)', v)
    if temp:
        result["temp"] = float(temp.group(1))

    return result


def compare_vitals(past_str: str, today_str: str, past_date: str) -> Optional[Dict[str, Any]]:
    """
    Compare past and today's vitals, return progress data with verdict.
    Returns dict with: lines, verdict, color, past_date
    Verdict: IMPROVING, WORSENING, or MIXED
    """
    past = extract_vitals_dict(past_str)
    today = extract_vitals_dict(today_str)
    if not past and not today:
        return None
    if not past or not today:
        return None

    lines = []
    overall_good = 0
    overall_bad = 0

    # BP Comparison
    if "sys" in past and "sys" in today:
        p_sys, t_sys = past["sys"], today["sys"]
        p_dia, t_dia = past.get("dia", 0), today.get("dia", 0)
        diff_sys = t_sys - p_sys
        if t_sys < 130:
            status = "✅ Controlled"
            overall_good += 1
        elif t_sys <= 140:
            status = "🟡 Borderline"
        else:
            status = "🔴 High"
            overall_bad += 1
        arrow = "↓" if diff_sys < 0 else ("↑" if diff_sys > 0 else "→")
        lines.append(
            f"**BP:** {p_sys}/{p_dia} → **{t_sys}/{t_dia}** mmHg  "
            f"{arrow} {abs(diff_sys)}  {status}"
        )

    # Sugar Comparison
    if "sugar" in past and "sugar" in today:
        p_sg, t_sg = past["sugar"], today["sugar"]
        diff_sg = t_sg - p_sg
        if t_sg < 140:
            status = "✅ Normal"
            overall_good += 1
        elif t_sg < 200:
            status = "🟡 Borderline"
        else:
            status = "🔴 High"
            overall_bad += 1
        arrow = "↓" if diff_sg < 0 else ("↑" if diff_sg > 0 else "→")
        lines.append(
            f"**Sugar:** {p_sg} → **{t_sg}** mg/dL  "
            f"{arrow} {abs(diff_sg)}  {status}"
        )

    # Weight Comparison
    if "weight" in past and "weight" in today:
        p_wt, t_wt = past["weight"], today["weight"]
        diff_wt = t_wt - p_wt
        arrow = "↓" if diff_wt < 0 else ("↑" if diff_wt > 0 else "→")
        if diff_wt < 0:
            status = "✅ Reduced"
            overall_good += 1
        elif diff_wt == 0:
            status = "→ Same"
        else:
            status = "⚠️ Increased"
        lines.append(
            f"**Weight:** {p_wt} → **{t_wt}** kg  "
            f"{arrow} {abs(diff_wt)} kg  {status}"
        )

    if not lines:
        return None

    if overall_bad == 0 and overall_good > 0:
        verdict = "🎉 **OVERALL: IMPROVING**"
        color = "success"
    elif overall_bad > overall_good:
        verdict = "⚠️ **OVERALL: WORSENING**"
        color = "error"
    else:
        verdict = "📊 **OVERALL: MIXED**"
        color = "warning"

    return {"lines": lines, "verdict": verdict, "color": color, "past_date": past_date}


def extract_phone_from_rx(rx_text: str) -> str:
    """Extract 10-digit phone number from prescription text."""
    m = re.search(r'\b\d{10}\b', rx_text)
    return m.group(0) if m else ""


def generate_csv(patients: List[Dict]) -> str:
    """Generate CSV string from patient records for OPD roster export."""
    lines = ["patient_name,phone,vitals,fee,date,complaints,medicines,specialty"]
    for p in patients:
        name = p.get("patient_name", "").replace('"', '""')
        phone = str(p.get("phone", "")).replace('"', '""')
        vitals = p.get("vitals", "").replace('"', '""')
        fee = str(p.get("fee", "0"))
        date = str(p.get("date", ""))[:10]
        complaints = p.get("complaints", "")[:50].replace('"', '""')
        medicines = p.get("medicines", "")[:80].replace('"', '""')
        specialty = p.get("specialty", "GP")
        lines.append(f'"{name}","{phone}","{vitals}","{fee}","{date}","{complaints}","{medicines}","{specialty}"')
    return "\n".join(lines)


def image_to_b64(img) -> str:
    """Convert PIL Image to base64 string for storage."""
    import base64
    buf = io.BytesIO()
    if hasattr(img, 'save'):
        img.save(buf, format='JPEG', quality=85)
        return base64.b64encode(buf.getvalue()).decode('utf-8')
    return ""


def b64_to_image_html(b64_str: str) -> str:
    """Convert base64 string to HTML img tag for Streamlit display."""
    return f'<img src="data:image/jpeg;base64,{b64_str}" style="max-width:100%;border-radius:8px;">'


def detect_conditions_from_complaints(complaints: str, vitals: str = "") -> list:
    """
    Simple keyword-based condition detection from complaints and vitals.
    Returns list of detected possible conditions.
    """
    text = f"{complaints} {vitals}".lower()
    conditions = []
    mapping = {
        "headache": ["Tension Headache", "Migraine"],
        "chest pain": ["Angina", "ACS (Acute Coronary Syndrome)"],
        "breathless": ["COPD", "Heart Failure", "Asthma"],
        "fever": ["URI", "UTI", "Typhoid"],
        "cough": ["URTI", "Bronchitis", "Pneumonia"],
        "stomach": ["Acid Peptic Disease", "GERD"],
        "sugar": ["Diabetes Mellitus"],
        "bp": ["Hypertension"],
        "joint": ["Osteoarthritis", "Rheumatoid Arthritis"],
        "back pain": ["Mechanical Back Pain", "Disc Prolapse"],
        "dizziness": ["Vertigo", "Orthostatic Hypotension"],
        "rash": ["Dermatitis", "Fungal Infection", "Allergy"],
        "weakness": ["Anemia", "Thyroid Disorder", "Electrolyte Imbalance"],
    }
    for keyword, conds in mapping.items():
        if keyword in text:
            conditions.extend(conds)
    return list(set(conditions))[:5]
