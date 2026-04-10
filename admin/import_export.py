"""
import_export.py — CSV/JSON data import for migrating old Google Sheet data.
Paste data directly and import into local SQLite database.
"""

import json
import logging

import streamlit as st
from database.sqlite_client import import_rows, get_all_patients_admin, get_all_licenses

log = logging.getLogger(__name__)


def render_import_tab():
    """Render the Import Old Data tab in admin panel."""
    st.markdown("### 📦 Import Old Patient Data")
    st.warning(
        "Google Sheet se data automatically nahi aata (Streamlit Cloud limitation). "
        "Ek baar manually import karo — hamesha ke liye DB mein save ho jaayega."
    )

    # Doctor selection
    import_options = {"Chief Doctor (Dr. Gill)": "chief"}
    for lic in get_all_licenses():
        import_options[f"{lic['doctor_name']} (ID: {lic['doctor_id']})"] = lic["doctor_id"]

    imp_doc = st.selectbox("Kiske liye import karein?", list(import_options.keys()), key="imp_doc_sel")
    imp_did = import_options[imp_doc]

    # CSV input
    csv_raw = st.text_area(
        "CSV data yahan paste karo:", height=160, key="csv_imp",
        placeholder="patient_name,phone,vitals,fee,date,complaints,medicines\n"
                    "Ramesh,9876543210,BP130/80,300,2026-03-01,Headache,1.Tab Paracetamol..."
    )

    # JSON input
    json_raw = st.text_area(
        "Ya JSON data yahan paste karo:", height=100, key="json_imp",
        placeholder='[{"patient_name":"Ramesh","phone":"9876543210","medicines":"1.Tab Amlodipine..."}]'
    )

    if st.button("🚀 Import Now", type="primary"):
        rows = []

        if json_raw.strip():
            try:
                parsed = json.loads(json_raw.strip())
                rows = parsed if isinstance(parsed, list) else [parsed]
            except Exception:
                st.error("JSON format galat hai. Check karo.")

        elif csv_raw.strip():
            lines = csv_raw.strip().split('\n')
            sep = '\t' if '\t' in lines[0] else ','
            hdrs = [h.strip().lower().replace(' ', '_') for h in lines[0].split(sep)]

            # Field mapping (flexible column names)
            FMAP = {
                "patient_name": ["patient_name", "name", "patient"],
                "phone": ["phone", "mobile", "contact", "telephone"],
                "vitals": ["vitals", "vital", "bp", "blood_pressure"],
                "fee": ["fee", "fees", "amount", "charges"],
                "date": ["date", "datetime", "visit_date"],
                "complaints": ["complaints", "complaint", "symptoms", "chief_complaints"],
                "medicines": ["medicines", "medicine", "prescription", "rx", "drugs"],
            }

            def find_col_index(headers, field):
                """Find column index for a field by trying multiple aliases."""
                for alias in FMAP.get(field, [field]):
                    for i, h in enumerate(headers):
                        if alias in h or h in alias:
                            return i
                return -1

            col_idx = {f: find_col_index(hdrs, f) for f in FMAP}

            for line in lines[1:]:
                if not line.strip():
                    continue
                cols = line.split(sep)

                def get_col(field):
                    i = col_idx.get(field, -1)
                    return cols[i].strip().strip('"') if 0 <= i < len(cols) else ""

                rows.append({
                    "patient_name": get_col("patient_name"),
                    "phone": get_col("phone"),
                    "vitals": get_col("vitals"),
                    "fee": get_col("fee"),
                    "date": get_col("date"),
                    "complaints": get_col("complaints"),
                    "medicines": get_col("medicines"),
                })

        if rows:
            n = import_rows(rows, imp_did)
            st.success(f"✅ **{n} patients imported** for {imp_doc}!")
        else:
            st.warning("Koi data nahi mila. CSV ya JSON paste karo.")

    # ── Verify DB Contents ────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🔍 Verify Database Contents")
    if st.button("📋 Show All Patients", key="show_all_db"):
        st.write("**Chief Doctor:**")
        chief_pts = get_all_patients_admin("chief")
        if chief_pts:
            st.success(f"{len(chief_pts)} patients")
            for p in chief_pts[:5]:
                st.caption(f"  • {p['patient_name']} | {str(p['date'])[:10]} | {p['medicines'][:50]}")
            if len(chief_pts) > 5:
                st.caption(f"  ...and {len(chief_pts) - 5} more")
        else:
            st.info("No patients found.")

        for lic in get_all_licenses():
            pts = get_all_patients_admin(lic["doctor_id"])
            if pts:
                st.write(f"**{lic['doctor_name']}:** {len(pts)} patients")
