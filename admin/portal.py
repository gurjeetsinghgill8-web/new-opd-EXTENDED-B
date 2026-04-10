"""
portal.py — Admin Portal with all admin tabs.
API Keys, Supabase Config, Licenses, Import, Stats, Waiting Room.
"""

import logging
from datetime import datetime, date, timedelta

import streamlit as st

import database.sqlite_client as db
import database.supabase_client as supa
import ai_engine.groq_client as ai

from admin.licenses import render_licenses_tab
from admin.import_export import render_import_tab
from admin.research_agent import render_research_agent

log = logging.getLogger(__name__)


def render_admin_portal():
    """
    Render the complete Admin Portal with 6 tabs.
    Only accessible when role == 'admin'.
    """
    t = st.tabs([
        "🔑 API Keys", "☁️ Supabase", "📋 Licenses",
        "📥 Import", "📊 Stats", "🪑 Waiting Room"
    ])

    # ══════════════════════════════════════════════════════════════════════
    # TAB 1: API KEY MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════
    with t[0]:
        st.subheader("🔑 Groq API Key Management")
        try:
            sett = db.get_settings()
            cur_key = sett.get("groq_api_key", "")
            if cur_key and len(cur_key) > 10:
                st.caption(f"Current: `{cur_key[:6]}...{cur_key[-4:]}`")
            else:
                st.warning("No API key configured. AI features won't work.")

            nk = st.text_input("New Groq API Key", type="password", key="adm_key",
                               placeholder="gsk_...")
            if st.button("💾 Save API Key", type="primary"):
                if nk.strip():
                    db.save_settings({"groq_api_key": nk.strip()})
                    st.success("API key saved! AI features enabled.")
                    st.rerun()
                else:
                    st.warning("Enter a valid key.")
        except Exception as e:
            log.error("API Key tab error: %s", e)
            st.error(str(e))

        st.markdown("---")
        st.subheader("🌐 Google Sheets Webhook")
        try:
            sett = db.get_settings()
            cur_webhook = sett.get("google_sheet_webhook", "")
            if cur_webhook:
                st.caption(f"Current: `{cur_webhook[:30]}...`")
            nw = st.text_input("Google Apps Script Webhook URL", value=cur_webhook, key="adm_webhook",
                               placeholder="https://script.google.com/...")
            if st.button("💾 Save Webhook URL"):
                if nw.strip():
                    db.save_settings({"google_sheet_webhook": nw.strip()})
                    st.success("Webhook URL saved!")
                    st.rerun()
        except Exception as e:
            log.error("Webhook error: %s", e)
            st.error(str(e))

    # ══════════════════════════════════════════════════════════════════════
    # TAB 2: SUPABASE CONFIGURATION
    # ══════════════════════════════════════════════════════════════════════
    with t[1]:
        st.subheader("☁️ Supabase Cloud Database Configuration")
        try:
            st.markdown(f"**Status:** {'🟢 Connected' if supa.is_configured() else '🔴 Not Configured'}")
            sett = db.get_settings()
            su = st.text_input("Supabase Project URL", value=sett.get("supabase_url", ""), key="su_url",
                               placeholder="https://xxxxx.supabase.co")
            sk = st.text_input("Supabase Anon Key", value=sett.get("supabase_key", ""),
                               type="password", key="su_key")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔌 Test Connection"):
                    db.save_settings({"supabase_url": su.strip(), "supabase_key": sk.strip()})
                    if supa.is_configured():
                        st.success("🟢 Connected! Cloud DB is active.")
                    else:
                        st.error("🔴 Not connected. Check URL and Key.")
            with c2:
                if st.button("🛠️ Init Tables"):
                    if supa.init_tables():
                        st.success("Tables initialised/verified!")
                    else:
                        st.warning("RPC failed. Tables may already exist or URL/Key is wrong.")
        except Exception as e:
            log.error("Supabase tab error: %s", e)
            st.error(str(e))

    # ══════════════════════════════════════════════════════════════════════
    # TAB 3: LICENSE MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════
    with t[2]:
        render_licenses_tab()

    # ══════════════════════════════════════════════════════════════════════
    # TAB 4: DATA IMPORT
    # ══════════════════════════════════════════════════════════════════════
    with t[3]:
        render_import_tab()

    # ══════════════════════════════════════════════════════════════════════
    # TAB 5: SYSTEM STATISTICS
    # ══════════════════════════════════════════════════════════════════════
    with t[4]:
        st.subheader("📊 System Statistics")
        try:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Patients", db.count_patients())
            c2.metric("Today's Patients", db.count_patients())
            c3.metric("AI Tokens Used",
                      ai.get_token_usage().get("prompt_tokens", 0) + ai.get_token_usage().get("completion_tokens", 0))

            # Per-doctor breakdown
            st.markdown("---")
            st.markdown("#### Per-Doctor Breakdown")
            licenses = db.get_all_licenses()
            dd = {"chief": "Chief Doctor", "junior": "Junior Doctor"}
            for lic in licenses:
                dd[lic["doctor_id"]] = lic["doctor_name"]

            for did_val, dname in dd.items():
                cnt = db.count_patients(did_val)
                if cnt > 0:
                    st.write(f"**{dname}:** {cnt} patients")

            # Session uptime
            if "login_time" in st.session_state:
                try:
                    lt = datetime.strptime(st.session_state["login_time"], "%Y-%m-%d %H:%M:%S")
                    uptime = datetime.now() - lt
                    st.metric("Session Uptime", str(uptime).split(".")[0])
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            log.error("Stats tab error: %s", e)
            st.error(str(e))

    # ══════════════════════════════════════════════════════════════════════
    # TAB 6: WAITING ROOM QUEUE
    # ══════════════════════════════════════════════════════════════════════
    with t[5]:
        st.subheader("🪑 Waiting Room Queue")
        try:
            st.session_state.setdefault("waiting_room", [])

            with st.form("wq_form"):
                wn = st.text_input("Patient Name", key="wq_name")
                if st.form_submit_button("➕ Add to Queue") and wn.strip():
                    st.session_state.waiting_room.append({
                        "name": wn.strip(),
                        "time": datetime.now().strftime("%H:%M"),
                        "status": "waiting"
                    })
                    st.rerun()

            q = sorted(st.session_state.waiting_room, key=lambda x: x["time"])
            if q:
                st.dataframe(
                    [{"#": i + 1, "Patient": p["name"], "Arrived": p["time"], "Status": p["status"]}
                     for i, p in enumerate(q)],
                    use_container_width=True, hide_index=True
                )
                rm = st.selectbox("Select patient:", [p["name"] for p in q], key="wq_sel")
                bc, bd = st.columns(2)
                with bc:
                    if st.button("✅ Mark Seen"):
                        for p in st.session_state.waiting_room:
                            if p["name"] == rm:
                                p["status"] = "seen"
                        st.rerun()
                with bd:
                    if st.button("❌ Remove"):
                        st.session_state.waiting_room = [
                            p for p in st.session_state.waiting_room if p["name"] != rm
                        ]
                        st.rerun()
            else:
                st.info("No patients in queue.")
        except Exception as e:
            log.error("Waiting room error: %s", e)
            st.error(str(e))
