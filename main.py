"""Bharat AI OPD - Self-healing entry point. Auto-creates __init__.py files."""
import os, logging, streamlit as st

# ── AUTO-FIX: Create __init__.py files if missing ──
_HERE = os.path.dirname(os.path.abspath(__file__))
for _pkg in ['config', 'database', 'ai_engine', 'features', 'admin', 'utils']:
    _d = os.path.join(_HERE, _pkg)
    os.makedirs(_d, exist_ok=True)
    _f = os.path.join(_d, '__init__.py')
    if not os.path.exists(_f):
        try:
            with open(_f, 'w') as _fh:
                _fh.write('# auto-generated\n')
        except Exception:
            pass

# ── Now import everything ──
import config.settings as settings
import database.sqlite_client as db
import database.supabase_client as supa
import database.sync_manager as sync
from features.login import render_login
from features.rx_form import render_rx_form
from features.patient_search import render_patient_search
from features.roster import render_roster
from features.specialty_upgrade import render_specialty_upgrade
from admin.portal import render_admin_portal

log = logging.getLogger(__name__)
st.set_page_config(page_title="Bharat AI OPD", page_icon="🏥", layout="wide")
db.init_db()
if "authenticated" not in st.session_state:
    render_login(); st.stop()
role: str = st.session_state.get("role", "junior")
with st.sidebar:
    st.title("🏥 " + settings.CLINIC_NAME)
    rc = "🔴" if role == "admin" else "🟢" if role == "chief" else "🔵"
    st.markdown(f"{rc} **{role.title()}**")
    tabs = ["📝 New Rx", "🔍 Search Patient", "📊 Roster", "⚕️ Specialty Upgrade", "🏥 Waiting Room"]
    if role == "admin": tabs.append("⚙️ Admin")
    choice = st.selectbox("Navigate", tabs, key="nav_tab")
    st.markdown("---")
    st.markdown("🟢 Local DB Active")
    st.markdown("🟢 Supabase" if supa.is_configured() else "🔴 Supabase Off")
    if st.button("🚪 Logout"):
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.rerun()
if not st.session_state.get("restored") and supa.is_configured():
    try: sync.sync_supabase_to_local(); st.session_state["restored"] = True
    except Exception as e: log.error("Auto-restore: %s", e)
try:
    if choice == "📝 New Rx": render_rx_form(role)
    elif choice == "🔍 Search Patient": render_patient_search()
    elif choice == "📊 Roster": render_roster(role)
    elif choice == "⚕️ Specialty Upgrade": render_specialty_upgrade()
    elif choice == "🏥 Waiting Room":
        st.session_state.setdefault("waiting_room", [])
        if st.session_state["waiting_room"]:
            wr = sorted(st.session_state["waiting_room"], key=lambda x: x["time"])
            st.dataframe([{"#": i+1, "Patient": p["name"], "Status": p["status"]} for i, p in enumerate(wr)], use_container_width=True)
        else: st.info("No patients waiting.")
    elif choice == "⚙️ Admin": render_admin_portal()
except Exception as e: log.error("Route: %s", e); st.error(f"Error: {e}")
