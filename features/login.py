"""
login.py — PIN-based authentication for Bharat AI OPD App.
Supports built-in roles (chief, junior, admin) and licensed doctor PINs.
Session state management after successful login.
"""

import logging
from datetime import datetime

import streamlit as st

from database.sqlite_client import verify_login_pin, get_all_licenses
from config.settings import FEATURE_FLAGS

log = logging.getLogger(__name__)


def render_login():
    """
    Render the login screen. Sets session_state on success.
    Handles: PIN input, verification, license expiry check, session init.
    """
    st.title("🏥 Bharat AI OPD")
    st.markdown("---")

    # ── Login Form ─────────────────────────────────────────────────────
    pin = st.text_input("Enter your 4-digit PIN", type="password", max_chars=8, key="login_pin",
                        placeholder="Your PIN")

    if st.button("🔐 Login", type="primary", use_container_width=True, key="login_btn"):
        if not pin:
            st.warning("PIN enter karo.")
            return

        result = verify_login_pin(pin)

        if not result:
            st.error("❌ Galat PIN ya expired license. Dobara try karo ya admin se contact karo.")
            return

        role = result["role"]
        did = result["doctor_id"]
        dname = result["doctor_name"]
        cname = result["clinic_name"]

        # ── License expiry warning (for licensed doctors) ────────────
        if role == "licensed":
            try:
                licenses = get_all_licenses()
                from datetime import date
                for lic in licenses:
                    if lic.get("doctor_id") == did:
                        exp_str = str(lic.get("expiry_date", ""))[:10]
                        try:
                            exp = date.fromisoformat(exp_str)
                            days_left = (exp - date.today()).days
                            if days_left <= 0:
                                st.error(f"❌ License expired on {exp_str}. Contact admin.")
                                return
                            elif days_left <= 7:
                                st.warning(f"⚠️ License expires in {days_left} days ({exp_str}).")
                        except ValueError:
                            pass
            except Exception as e:
                log.error("License check error: %s", e)

        # ── Set Session State ─────────────────────────────────────────
        st.session_state.logged_in = True
        st.session_state.role = role
        st.session_state.doctor_id = did
        st.session_state.doctor_name = dname
        st.session_state.clinic_name = cname
        st.session_state.login_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.rx_count_today = 0
        st.session_state.waiting_queue = []

        # For licensed doctors, store license info
        if role == "licensed":
            st.session_state.lic = {
                "doctor_name": dname,
                "clinic_name": cname,
                "specialty": result.get("specialty", ""),
            }

        log.info("Login success — role=%s, doctor_id=%s", role, did)
        st.success(f"Welcome, {dname}! 🎉")
        st.rerun()
