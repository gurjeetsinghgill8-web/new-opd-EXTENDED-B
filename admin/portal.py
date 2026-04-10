"""Admin Portal — API keys, Supabase, licenses, import, stats, waiting room."""
import logging, csv, json, io
from datetime import date, datetime
import streamlit as st
import config.settings as settings
import database.sqlite_client as db
import database.supabase_client as supa
import ai_engine.groq_client as ai
log = logging.getLogger(__name__)
def render_admin_portal() -> None:
    """Admin panel — sab features yahan se control hote hain."""
    t = st.tabs(["🔑 API Keys", "☁️ Supabase", "📋 Licenses", "📥 Import", "📊 Stats", "🪑 Waiting"])
    with t[0]:  # API Key — masked save via DB
        st.subheader("Groq API Key")
        try:
            cur = settings.GROQ_API_KEY or ""
            st.caption(f"Current: `{cur[:6]}...{cur[-4:]}`" if len(cur) > 10 else "Current: Not set")
            nk = st.text_input("New Key", type="password", key="adm_key")
            if st.button("💾 Save Key") and nk.strip():
                db.save_settings({"groq_api_key": nk.strip()}); log.info("Key saved"); st.success("Saved!")
        except Exception as e: log.error("Key: %s", e); st.error(str(e))
    with t[1]:  # Supabase — URL/Key test aur init
        st.subheader("Supabase Configuration")
        try:
            st.markdown(f"**Status:** {'🟢 Connected' if supa.is_configured() else '🔴 Not Configured'}")
            su = st.text_input("URL", settings.SUPABASE_URL or "", key="su_url")
            sk = st.text_input("Anon Key", value=settings.SUPABASE_KEY or "", type="password", key="su_key")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔌 Test"):
                    db.save_settings({"supabase_url": su.strip(), "supabase_key": sk.strip()})
                    st.markdown("🟢 Connected" if supa.is_configured() else "🔴 Not Configured")
            with c2:
                if st.button("🛠️ Init"): supa.init_tables(); st.success("Done!")
        except Exception as e: log.error("Supa: %s", e); st.error(str(e))
    with t[2]:  # License CRUD — create, list, extend, delete
        st.subheader("License Management")
        try:
            with st.form("lic_form"):
                lk = st.text_input("License Key", key="lk")
                dn = st.text_input("Doctor Name", key="dn")
                exp = st.date_input("Expiry", key="ld_exp")
                rl = st.selectbox("Role", ["chief", "junior"], key="lk_role")
                if st.form_submit_button("➕ Create") and lk.strip():
                    db.save_license(lk.strip(), dn.strip(), str(exp)); st.success("Created!")
            lics = db.get_licenses() if hasattr(db, "get_licenses") else []
            if lics:
                rows = [{"Key": str(l.get("license_key", ""))[:12] + "...", "Doctor": l.get("doctor_name", ""),
                         "Expiry": l.get("expiry_date", ""), "Role": l.get("role", ""),
                         "Status": "🟢 Active" if date.fromisoformat(str(l.get("expiry_date", "2000-01-01"))) >= date.today() else "🔴 Expired"} for l in lics]
                st.dataframe(rows, use_container_width=True)
                sel = st.selectbox("Select License", [l.get("license_key", "") for l in lics], key="sl_lic")
                ne = st.date_input("New Expiry", key="ne_exp"); bc, bd = st.columns(2)
                with bc:
                    if st.button("⏳ Extend"):
                        for l in lics:
                            if l.get("license_key") == sel:
                                db.delete_license(sel); db.save_license(sel, l.get("doctor_name", ""), str(ne))
                                st.success("Extended!"); st.rerun()
                with bd:
                    if st.button("🗑️ Delete"): db.delete_license(sel); st.success("Deleted!"); st.rerun()
            else: st.info("No licenses found.")
        except Exception as e: log.error("Lic: %s", e); st.error(str(e))
    with t[3]:  # CSV/JSON Import — parse aur bulk insert
        st.subheader("Bulk Patient Import")
        try:
            up = st.file_uploader("CSV/JSON", type=["csv", "json"], key="imp_file")
            if up:
                raw = up.read().decode()
                # CSV ya JSON dono format support
                data = list(csv.DictReader(io.StringIO(raw))) if up.name.endswith(".csv") else json.loads(raw)
                st.info(f"{len(data)} records found"); ok = err = 0; pr = st.progress(0)
                for i, r in enumerate(data):
                    try:
                        db.insert_patient({"name": r.get("name", ""), "age": str(r.get("age", "")),
                                           "phone": r.get("phone", ""), "gender": r.get("gender", "M"),
                                           "address": r.get("address", "")}); ok += 1
                    except Exception: err += 1
                    pr.progress((i + 1) / len(data), f"{i + 1}/{len(data)}")
                pr.empty(); st.success(f"✅ {ok} inserted, ❌ {err} failed")
        except Exception as e: log.error("Imp: %s", e); st.error(str(e))
    with t[4]:  # System Stats — patients, Rx, drugs, AI tokens, uptime
        st.subheader("System Statistics")
        try:
            c1, c2, c3 = st.columns(3)
            c1.metric("Patients", db.count_patients() if hasattr(db, "count_patients") else "—")
            c2.metric("Prescriptions", db.count_prescriptions() if hasattr(db, "count_prescriptions") else "—")
            c3.metric("Drugs", db.count_drugs() if hasattr(db, "count_drugs") else "—")
            c4, c5 = st.columns(2)
            tk = ai.get_token_usage() if hasattr(ai, "get_token_usage") else {}
            c4.metric("AI Tokens", tk.get("prompt_tokens", 0) + tk.get("completion_tokens", 0))
            if "login_time" in st.session_state:
                try:
                    lt = datetime.strptime(st.session_state["login_time"], "%Y-%m-%d %H:%M:%S")
                    c5.metric("Uptime", str(datetime.now() - lt).split(".")[0])
                except (ValueError, TypeError): pass
        except Exception as e: log.error("Stats: %s", e); st.error(str(e))
    with t[5]:  # Waiting Room — add, seen, remove; auto-sort by time
        st.subheader("Waiting Room Queue")
        try:
            st.session_state.setdefault("waiting_room", [])
            with st.form("wq_form"):
                wn = st.text_input("Patient Name", key="wq_name")
                if st.form_submit_button("➕ Add") and wn.strip():
                    st.session_state.waiting_room.append({"name": wn.strip(), "time": datetime.now().isoformat(), "status": "waiting"}); st.rerun()
            q = sorted(st.session_state.waiting_room, key=lambda x: x["time"])
            if q:
                st.dataframe([{"#": i + 1, "Patient": p["name"], "Arrived": p["time"][:19], "Status": p["status"]} for i, p in enumerate(q)], use_container_width=True)
                rm = st.selectbox("Select", [p["name"] for p in q], key="wq_sel"); bc, bd = st.columns(2)
                with bc:
                    if st.button("✅ Seen"):
                        for p in st.session_state.waiting_room:
                            if p["name"] == rm: p["status"] = "seen"
                        st.rerun()
                with bd:
                    if st.button("❌ Remove"):
                        st.session_state.waiting_room = [p for p in st.session_state.waiting_room if p["name"] != rm]; st.rerun()
            else: st.info("No patients in queue.")
        except Exception as e: log.error("Wait: %s", e); st.error(str(e))
