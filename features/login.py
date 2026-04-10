"""Login Feature — PIN-based authentication aur session management."""
import logging
from datetime import datetime

import streamlit as st

import config.settings as settings
import database.sqlite_client as db

log = logging.getLogger(__name__)


def render_login() -> str | None:
    """PIN verify karke role return karta hai; None agar fail. Logout bhi yahi handle."""
    # ── Agar pehle se logged in hai toh dashboard view ─────────────────────────
    if st.session_state.get("authenticated"):
        role: str = st.session_state.get("role", "unknown")
        st.markdown(f"### ✅ Logged in as **{role.title()}**  ")
        login_time = st.session_state.get("login_time", "")
        if login_time:
            st.caption(f"Login time: {login_time}")
        if st.button("🚪 Logout"):
            # Saara session state clear kar dete hain — fresh start ke liye
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        return role

    # ── Login form ─────────────────────────────────────────────────────────────
    st.title("🏥 Bharat AI OPD")
    st.markdown("---")
    pin = st.text_input("Enter your 4-digit PIN", type="password", max_chars=4)

    if st.button("🔐 Login"):
        try:
            if not pin:
                st.warning("PIN enter karo."); return None
            # PIN ko role se match karo — settings.PINS = {role: pin}
            matched_role: str | None = None
            for r, p in settings.PINS.items():
                if pin.strip() == p:
                    matched_role = r; break
            if not matched_role:
                st.error("❌ Galat PIN — dobara try karo."); return None
            # ── License expiry check (admin ke liye nahi) ───────────────────────
            if matched_role != "admin":
                try:
                    licenses = db.get_licenses()
                    from datetime import datetime as _dt
                    now = _dt.now()
                    for lic in licenses:
                        exp = lic.get("expiry_date", "")
                        if exp:
                            try:
                                if _dt.strptime(exp, "%Y-%m-%d") < now:
                                    st.warning(
                                        f"⚠️ License expired for {lic.get('doctor_name','N/A')} "
                                        f"on {exp}. Contact admin.")
                            except ValueError:
                                log.warning("Invalid expiry date format: %s", exp)
                except Exception as e:
                    log.error("License check failed: %s", e)
            # ── Session state set karo ──────────────────────────────────────────
            st.session_state["authenticated"] = True
            st.session_state["role"] = matched_role
            st.session_state["login_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.session_state["rx_count_today"] = 0
            st.session_state["current_patient"] = None
            st.session_state["selected_drugs"] = []
            st.session_state["editing_rx"] = None
            st.success(f"Welcome, {matched_role.title()}! 🎉")
            log.info("Login success — role=%s", matched_role)
            st.rerun()
            return matched_role
        except Exception as e:
            log.error("Login error: %s", e)
            st.error("Login mein error aaya. Check logs."); return None
    return None
