"""Roster — Doctor visit dashboard. Date range se visits dekhte hain, revenue calculate karte hain."""
import logging, re
from datetime import date, timedelta
import streamlit as st
from config import settings as settings
from database import sqlite_client as db
from utils import helpers as helpers

log = logging.getLogger(__name__)

DEFAULT_FEE: float = 500.0  # Jab fee string parse na ho to default ₹500 lagao


def _extract_bp(vitals_str: str) -> tuple[int, int] | None:
    """Vitals string se systolic/diastolic BP extract karta hai, e.g. 'BP 130/85 mmHg'."""
    if not vitals_str:
        return None
    match = re.search(r"(\d{2,3})\s*/\s*(\d{2,3})", vitals_str)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _calc_fee(drugs_str: str) -> float:
    """Drug string ya default fee se visit ka revenue estimate nikalta hai."""
    if not drugs_str:
        return DEFAULT_FEE
    try:
        return helpers.clean_fee_string(drugs_str)
    except Exception:
        return DEFAULT_FEE


def render_roster(doctor_role: str) -> None:
    """Doctor dashboard — visits, revenue, vitals trend, follow-ups sab ek jagah dikhata hai."""
    try:
        st.subheader("📋 Doctor Roster & Analytics")
        today = date.today()
        default_end = today + timedelta(days=30)
        col_d1, col_d2 = st.columns(2)
        start_date = col_d1.date_input("Start Date", today, key="roster_start")
        end_date = col_d2.date_input("End Date", default_end, key="roster_end")

        if start_date > end_date:
            st.warning("Start date end date se pehle hona chahiye.")
            return

        # ── DB se prescriptions fetch karo (junior sirf apne dekh sakta) ──
        params: tuple = (str(start_date), str(end_date))
        if doctor_role == "junior":
            doc = st.session_state.get("doctor_name", "")
            rows = db._fetch(
                "SELECT p.*, r.id AS rx_id, r.doctor, r.complaints, r.vitals, "
                "r.drugs, r.follow_up, r.date AS rx_date "
                "FROM prescriptions r JOIN patients p ON r.patient_id=p.id "
                "WHERE r.date BETWEEN ? AND ? AND r.doctor=? ORDER BY r.date",
                (*params, doc),
            )
        else:
            rows = db._fetch(
                "SELECT p.*, r.id AS rx_id, r.doctor, r.complaints, r.vitals, "
                "r.drugs, r.follow_up, r.date AS rx_date "
                "FROM prescriptions r JOIN patients p ON r.patient_id=p.id "
                "WHERE r.date BETWEEN ? AND ? ORDER BY r.date", params,
            )

        if not rows:
            st.info("Is date range mein koi visit nahi mili.")
            return

        # ── Summary Metric Cards ──
        total_visits = len(rows)
        total_revenue = sum(_calc_fee(r.get("drugs", "")) for r in rows)
        num_days = max((end_date - start_date).days, 1)
        avg_per_day = total_revenue / num_days
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Visits", total_visits)
        m2.metric("Estimated Revenue", f"₹{total_revenue:,.0f}")
        m3.metric("Avg Revenue/Day", f"₹{avg_per_day:,.0f}")

        # ── Vitals Trend: BP systolic/diastolic line chart ──
        sys_vals: list[int] = []
        dia_vals: list[int] = []
        for r in rows:
            bp = _extract_bp(r.get("vitals", ""))
            if bp:
                sys_vals.append(bp[0])
                dia_vals.append(bp[1])
        if sys_vals:
            st.subheader("📊 BP Trend (Systolic / Diastolic)")
            st.line_chart({"Systolic": sys_vals, "Diastolic": dia_vals})

        # ── Visit Timeline: day-wise expander ──
        st.subheader("📅 Visit Timeline")
        for r in rows:
            d = r.get("rx_date", "")[:10]
            with st.expander(f"{d} — {r.get('name', 'Unknown')}"):
                st.write(f"**Complaints:** {r.get('complaints', 'N/A')}")
                st.write(f"**Drugs:** {r.get('drugs', 'N/A')}")
                if st.button("✏️ Edit", key=f"edit_rx_{r.get('rx_id', 0)}"):
                    st.session_state["edit_rx_id"] = r.get("rx_id")
                    st.session_state["page"] = "rx_form"
                    st.rerun()

        # ── Follow-up List: next 7 days mein jo follow-ups hain ──
        cutoff = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        followups = [r for r in rows if r.get("follow_up", "") <= cutoff]
        if followups:
            st.subheader("🔁 Follow-ups (Next 7 Days)")
            st.dataframe(
                {"Date": [f.get("follow_up", "") for f in followups],
                 "Patient": [f.get("name", "") for f in followups],
                 "Phone": [f.get("phone", "") for f in followups]},
                use_container_width=True,
            )
    except Exception as e:
        log.error("render_roster error: %s", e, exc_info=True)
        st.error(f"Roster load mein error aaya: {e}")
