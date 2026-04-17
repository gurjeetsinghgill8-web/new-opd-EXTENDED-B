"""
main.py — Bharat AI OPD App — Main Entry Point
Thin router only. NO business logic here. All features imported from modules.
"""

import os
import re
import datetime
import logging

import streamlit as st
from datetime import timedelta

# ── Logging ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')

# ── Initialize modules ──────────────────────────────────────────────────
from config.settings import GOOGLE_SHEET_WEBHOOK
from database.sqlite_client import (
    init_db, get_settings, get_patients_filter, search_patients,
    get_starred, count_pending, save_patient,
)
from database.supabase_client import _supa_available
from database.sync_manager import sync_from_supabase, fetch_sheet_data
from features.login import render_login
from features.patient_form import render_rx_form
from features.batch_scan import render_batch_scan
from features.starred import render_starred
from features.pdf_generator import make_rx_pdf
from utils.helpers import clean_fee, compare_vitals, generate_csv

# ── Page Config ─────────────────────────────────────────────────────────
st.set_page_config(page_title="Bharat AI OPD", page_icon="🩺", layout="wide")

# ── Init Database ───────────────────────────────────────────────────────
init_db()

# ── Session State Initialization ────────────────────────────────────────
for k, v in [
    ("logged_in", False), ("role", None), ("doctor_id", None),
    ("waiting_queue", []), ("roster_data", []),
]:
    if k not in st.session_state:
        st.session_state[k] = v


# ══════════════════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════════════════
if not st.session_state.logged_in:
    render_login()
    st.stop()  # Stop execution — don't render dashboard below


# ══════════════════════════════════════════════════════════════════════════
# ADMIN PORTAL (separate routing)
# ══════════════════════════════════════════════════════════════════════════
if st.session_state.role == "admin":
    from admin.portal import render_admin_portal
    render_admin_portal()
    st.stop()


# ══════════════════════════════════════════════════════════════════════════
# DOCTOR PORTAL (Chief / Licensed / Junior)
# ══════════════════════════════════════════════════════════════════════════
role = st.session_state.role
did = st.session_state.doctor_id
is_chief = role == "chief"
is_lic = role == "licensed"
is_junior = role == "junior"
sett = get_settings()

# ── Header ──────────────────────────────────────────────────────────────
hc1, hc2 = st.columns([5, 1])
with hc1:
    if is_chief:
        st.title("🩺 Bharat AI Clinic — Chief Doctor")
    elif is_lic:
        lic = st.session_state.get("lic", {})
        st.title(f"🩺 {lic.get('clinic_name', 'Bharat AI Clinic')} — {lic.get('doctor_name', 'Doctor')}")
    else:
        st.title("🩺 Bharat AI Clinic — Junior Doctor")
with hc2:
    if st.button("🔒 Logout", use_container_width=True, key="logout_btn"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ── DB Status Badge ─────────────────────────────────────────────────────
if _supa_available():
    st.success("☁️ **Cloud DB: Connected** — Data saves permanently", icon="✅")
else:
    st.warning("⚠️ **Cloud DB: NOT connected** — Data saves locally + Google Sheet backup only.")

# ── Sync from Supabase on login ─────────────────────────────────────────
sync_from_supabase()

# ── Pending Rx Badge ────────────────────────────────────────────────────
pending_n = count_pending(did)
if pending_n > 0:
    st.warning(f"📋 **{pending_n} prescription(s)** pending review in Batch Scan tab →")

# ── Auto-restore check ─────────────────────────────────────────────────
def _check_and_restore():
    """Check if local DB is empty after server restart, offer restore from cloud."""
    c = st.session_state.get("_conn")
    try:
        from database.sqlite_client import _conn
        conn = _conn()
        count = conn.execute("SELECT COUNT(*) FROM patients WHERE doctor_id=?", (did,)).fetchone()[0]
        conn.close()
        if count == 0:
            st.warning("⚠️ **Local data empty** (server restarted). Data is safe in cloud.")
            if st.button("🔄 Restore from Cloud", type="primary", key="restore_btn"):
                with st.spinner("Restoring..."):
                    from database.sync_manager import restore_from_cloud
                    restored = restore_from_cloud(did)
                    if restored:
                        st.success(f"✅ {len(restored)} patients restored!")
                        st.rerun()
                    else:
                        st.error("No data found in cloud.")
    except Exception:
        pass

_check_and_restore()

# ══════════════════════════════════════════════════════════════════════════
# TAB LAYOUT
# ══════════════════════════════════════════════════════════════════════════
if is_chief:
    tb_new, tb_batch, tb_star, tb_roster, tb_settings, tb_research = st.tabs([
        "📝 New Rx", "📸 Batch Scan", "⭐ Starred",
        "👥 OPD Roster", "⚙️ Settings", "📊 Research"
    ])
else:
    tb_new, tb_batch, tb_star, tb_roster, tb_settings = st.tabs([
        "📝 New Rx", "📸 Batch Scan", "⭐ Starred",
        "👥 OPD Roster", "⚙️ Settings"
    ])


# ══════════════════════════════════════════════════════════════════════════
# TAB: NEW Rx (Patient Form + AI Prescription)
# ══════════════════════════════════════════════════════════════════════════
with tb_new:
    pt_mode_key = "pt_mode_selection"
    if pt_mode_key not in st.session_state:
        st.session_state[pt_mode_key] = "new"

    m1, m2, m3 = st.columns([1, 1, 2])
    with m1:
        if st.button("🆕 New Patient", use_container_width=True,
                     type="primary" if st.session_state[pt_mode_key] == "new" else "secondary",
                     key="btn_new_pt"):
            st.session_state[pt_mode_key] = "new"
            # Clear form state
            for k in list(st.session_state.keys()):
                if any(k.startswith(p) for p in ["pre_", "rx_main", "notes_", "upgrades_",
                                                   "sel_specs_", "show_upg_", "inv_", "cam_",
                                                   "opt_", "cme_", "chat_", "cme_topics_",
                                                   "cme_chat_"]):
                    st.session_state.pop(k, None)
            for k in ["is_followup", "past_vitals", "past_rx", "past_date"]:
                st.session_state.pop(k, None)
            st.rerun()
    with m2:
        if st.button("👤 Old Patient", use_container_width=True,
                     type="primary" if st.session_state[pt_mode_key] == "old" else "secondary",
                     key="btn_old_pt"):
            st.session_state[pt_mode_key] = "old"
            st.rerun()
    with m3:
        if st.session_state.get("is_followup"):
            st.success(
                f"🔄 Follow-Up loaded: **{st.session_state.get('pre_name', '')}** "
                f"(Past: {st.session_state.get('past_date', '')})"
            )

    # ── Old Patient Search ──────────────────────────────────────────
    if st.session_state[pt_mode_key] == "old":
        st.markdown("---")
        st.markdown("### 👤 Search Old Patient")
        op_q = st.text_input("🔎 Name ya Phone:", key="old_pt_search",
                             placeholder="e.g. Ramesh ya 9876543210")
        if op_q and len(op_q) >= 2:
            with st.spinner("Searching..."):
                op_results = search_patients(op_q, did)
            if op_results:
                st.success(f"🔍 {len(op_results)} record(s) mila")
                for idx, pt in enumerate(op_results):
                    src_tag = "📱 DB"
                    with st.expander(
                        f"👤 {pt['patient_name']} | {str(pt['date'])[:10]} | "
                        f"📞 {pt['phone']} | {src_tag}"
                    ):
                        st.write(f"**Vitals:** {pt['vitals']} | **Fee:** ₹{pt['fee']}")
                        if pt.get('complaints'):
                            st.caption(f"C/O: {pt['complaints'][:120]}")
                        st.info(pt['medicines'] or "No Rx data")
                        oa1, oa2, oa3 = st.columns(3)
                        with oa1:
                            if st.button("📝 Follow-Up Rx", key=f"opfu_{idx}",
                                         use_container_width=True, type="primary"):
                                st.session_state["pre_name"] = pt["patient_name"]
                                st.session_state["pre_phone"] = pt["phone"]
                                st.session_state["pre_fee"] = pt.get("fee", "300")
                                st.session_state["past_vitals"] = pt["vitals"]
                                st.session_state["past_rx"] = pt["medicines"]
                                st.session_state["past_date"] = str(pt["date"])[:10]
                                st.session_state["is_followup"] = True
                                st.session_state.pop("rx_main", None)
                                st.session_state.pop("notes_main", None)
                                st.session_state[pt_mode_key] = "new"
                                st.rerun()
                        with oa2:
                            if st.button("✏️ Edit / Reprint", key=f"opedit_{idx}",
                                         use_container_width=True):
                                st.session_state["pre_name"] = pt["patient_name"]
                                st.session_state["pre_phone"] = pt["phone"]
                                st.session_state["pre_vitals"] = pt["vitals"]
                                st.session_state["pre_fee"] = pt.get("fee", "300")
                                st.session_state["rx_main"] = pt["medicines"]
                                st.session_state[pt_mode_key] = "new"
                                st.rerun()
                        with oa3:
                            old_pdf = make_rx_pdf(pt["patient_name"], pt["vitals"], pt["medicines"])
                            st.download_button(
                                "📄 Old PDF", data=old_pdf,
                                file_name=f"{pt['patient_name']}_OldRx.pdf",
                                mime="application/pdf", key=f"opdl_{idx}",
                                use_container_width=True
                            )
            else:
                st.warning(f"'{op_q}' ka koi record nahi mila.")
        st.markdown("---")

    # ── Show New Rx Form ────────────────────────────────────────────
    if st.session_state[pt_mode_key] == "new":
        render_rx_form(uid="main")


# ══════════════════════════════════════════════════════════════════════════
# TAB: BATCH SCAN
# ══════════════════════════════════════════════════════════════════════════
with tb_batch:
    render_batch_scan()


# ══════════════════════════════════════════════════════════════════════════
# TAB: STARRED
# ══════════════════════════════════════════════════════════════════════════
with tb_star:
    render_starred()


# ══════════════════════════════════════════════════════════════════════════
# TAB: OPD ROSTER (Patient Search + Daily Log + Visit History + Charts)
# ══════════════════════════════════════════════════════════════════════════
with tb_roster:
    st.markdown("### 🔍 Patient Search")
    sq = st.text_input("🔎 Name ya Phone:", key="sq", placeholder="Ramesh ya 9876543210")
    if sq and len(sq) >= 2:
        res = search_patients(sq, did)
        if res:
            st.success(f"🔍 {len(res)} record(s) mila")
            for idx, pt in enumerate(res):
                with st.expander(
                    f"👤 {pt['patient_name']} | {str(pt['date'])[:10]} | {pt['phone']}"
                ):
                    st.write(f"Vitals: {pt['vitals']} | Fee: ₹{pt['fee']}")
                    if pt.get('complaints'):
                        st.caption(f"C/O: {pt['complaints'][:100]}")
                    st.info(pt['medicines'])
                    rb1, rb2 = st.columns(2)
                    with rb1:
                        if st.button("📝 Follow-Up", key=f"sfu_{idx}"):
                            st.session_state["pre_name"] = pt["patient_name"]
                            st.session_state["pre_phone"] = pt["phone"]
                            st.session_state["pre_fee"] = pt["fee"]
                            st.session_state["past_vitals"] = pt["vitals"]
                            st.session_state["past_rx"] = pt["medicines"]
                            st.session_state["past_date"] = str(pt["date"])[:10]
                            st.session_state["is_followup"] = True
                            st.session_state.pop("rx_main", None)
                            st.success("✅ Loaded! 📝 New Rx tab mein jayen.")
                    with rb2:
                        if st.button("✏️ Edit Rx", key=f"sedit_{idx}"):
                            st.session_state["pre_name"] = pt["patient_name"]
                            st.session_state["pre_phone"] = pt["phone"]
                            st.session_state["pre_vitals"] = pt["vitals"]
                            st.session_state["pre_fee"] = pt["fee"]
                            st.session_state["rx_main"] = pt["medicines"]
                            st.success("✅ Loaded! 📝 New Rx tab mein jayen.")
        else:
            st.warning(f"'{sq}' ka koi record nahi mila.")

    st.markdown("---")
    st.markdown("### 📅 Daily OPD Roster")
    df1, df2 = st.columns([3, 1])
    with df1:
        date_f = st.radio("Range:", ["Today", "Yesterday", "Last 5 Days", "All Time"], horizontal=True)
    with df2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📥 Fetch Roster", type="primary", use_container_width=True):
            today = datetime.date.today()
            db_pts = get_patients_filter(date_f, did)
            for p in db_pts:
                p["_source"] = "db"
            combined = list(db_pts)

            # Also fetch from Google Sheet if webhook configured
            webhook = get_settings().get("google_sheet_webhook", "")
            if webhook.startswith("http"):
                with st.spinner("☁️ Google Sheet se purana data fetch kar rahe hain..."):
                    all_sheet, _ = fetch_sheet_data()
                    if all_sheet:
                        sheet_pts = []
                        for row in all_sheet:
                            date_raw = row.get("date", "")
                            row_date = None
                            try:
                                m2 = re.search(r'(\d{4})-(\d{2})-(\d{2})', str(date_raw))
                                if m2:
                                    row_date = datetime.date(
                                        int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
                                    )
                            except Exception:
                                pass
                            inc = False
                            if date_f == "All Time":
                                inc = True
                            elif row_date:
                                if date_f == "Today" and row_date == today:
                                    inc = True
                                elif date_f == "Yesterday" and row_date == today - timedelta(days=1):
                                    inc = True
                                elif date_f == "Last 5 Days" and 0 <= (today - row_date).days <= 5:
                                    inc = True
                            if inc:
                                sheet_pts.append(row)
                        combined.extend(sheet_pts)

            combined.sort(key=lambda p: str(p.get("date", ""))[:10], reverse=True)
            st.session_state.roster_data = combined

            if not combined:
                st.warning("Koi patient nahi mila.")
            else:
                db_n = len(db_pts)
                sh_n = len(combined) - db_n
                st.success(f"✅ **{len(combined)} records** (📱 {db_n} DB + ☁️ {sh_n} Google Sheet)")

    # ── Display Roster Data ─────────────────────────────────────────
    if st.session_state.get("roster_data"):
        pts = st.session_state.roster_data
        m1, m2 = st.columns(2)
        m1.metric("👥 Total Patients", len(pts))
        m2.metric("💰 Total Revenue", f"₹{sum(clean_fee(p['fee']) for p in pts):,}")

        # CSV Export
        csv_data = generate_csv(pts)
        st.download_button(
            "📥 Export CSV", data=csv_data,
            file_name=f"OPD_Roster_{datetime.date.today()}.csv", mime="text/csv"
        )

        st.markdown("---")
        for idx, pt in enumerate(pts):
            src_tag = "☁️ Sheet" if pt.get("_source") == "sheet" else "📱 DB"
            with st.expander(
                f"👤 {pt['patient_name']} | {str(pt['date'])[:10]} | "
                f"₹{pt['fee']} | {pt.get('specialty', 'GP')} | {src_tag}"
            ):
                st.write(f"📞 {pt['phone']} | Vitals: {pt['vitals']}")
                if pt.get('complaints'):
                    st.caption(f"C/O: {pt['complaints'][:100]}")
                st.info(pt['medicines'])

                # ── Visit History Timeline with Charts ──────────────
                all_visits = search_patients(pt['patient_name'], did)
                if len(all_visits) > 1:
                    with st.expander(
                        f"📈 {pt['patient_name']} — All {len(all_visits)} Visits", expanded=False
                    ):
                        import pandas as pd
                        from utils.helpers import extract_vitals_dict

                        bp_dates, bp_sys_list, sugar_list, weight_list = [], [], [], []
                        for v in reversed(all_visits):
                            vd = extract_vitals_dict(v.get("vitals", ""))
                            bp_dates.append(str(v.get("date", ""))[:10])
                            bp_sys_list.append(vd.get("sys", None))
                            sugar_list.append(vd.get("sugar", None))
                            weight_list.append(vd.get("weight", None))

                        has_bp = any(x is not None for x in bp_sys_list)
                        has_sg = any(x is not None for x in sugar_list)
                        has_wt = any(x is not None for x in weight_list)

                        if has_bp or has_sg or has_wt:
                            tc1, tc2, tc3 = st.columns(3)
                            if has_bp:
                                bp_vals = [x for x in bp_sys_list if x is not None]
                                bp_lbls = [bp_dates[i] for i, x in enumerate(bp_sys_list) if x is not None]
                                tc1.markdown("**BP Systolic Trend**")
                                tc1.line_chart(pd.DataFrame({"BP (mmHg)": bp_vals}, index=bp_lbls))
                            if has_sg:
                                sg_vals = [x for x in sugar_list if x is not None]
                                sg_lbls = [bp_dates[i] for i, x in enumerate(sugar_list) if x is not None]
                                tc2.markdown("**Sugar Trend**")
                                tc2.line_chart(pd.DataFrame({"Sugar (mg/dL)": sg_vals}, index=sg_lbls))
                            if has_wt:
                                wt_vals = [x for x in weight_list if x is not None]
                                wt_lbls = [bp_dates[i] for i, x in enumerate(weight_list) if x is not None]
                                tc3.markdown("**Weight Trend**")
                                tc3.line_chart(pd.DataFrame({"Weight (kg)": wt_vals}, index=wt_lbls))

                        # Visit history list
                        for vidx, v in enumerate(all_visits):
                            v_date = str(v.get("date", ""))[:10]
                            st.markdown(
                                f"**Visit {len(all_visits) - vidx}** — {v_date} | "
                                f"{v.get('specialty', 'GP')} | ₹{v.get('fee', '0')}"
                            )
                            with st.expander(f"📋 Rx — {v_date}", expanded=False):
                                st.text(v.get("medicines", "No data"))
                            st.divider()

                # ── Action Buttons ──────────────────────────────────
                rb1, rb2 = st.columns(2)
                with rb1:
                    if st.button("📝 Follow-Up", key=f"rfu_{idx}"):
                        st.session_state["pre_name"] = pt["patient_name"]
                        st.session_state["pre_phone"] = pt["phone"]
                        st.session_state["pre_fee"] = "200"
                        st.session_state["past_vitals"] = pt["vitals"]
                        st.session_state["past_rx"] = pt["medicines"]
                        st.session_state["past_date"] = str(pt["date"])[:10]
                        st.session_state["is_followup"] = True
                        st.session_state.pop("rx_main", None)
                        st.success("✅ Follow-up loaded!")
                with rb2:
                    if st.button("✏️ Edit", key=f"redit_{idx}"):
                        st.session_state["pre_name"] = pt["patient_name"]
                        st.session_state["pre_phone"] = pt["phone"]
                        st.session_state["pre_vitals"] = pt["vitals"]
                        st.session_state["pre_fee"] = pt["fee"]
                        st.session_state["rx_main"] = pt["medicines"]
                        st.success("✅ Loaded for editing!")


# ══════════════════════════════════════════════════════════════════════════
# TAB: SETTINGS (Clinic Info, Doctor Profile, Templates)
# ══════════════════════════════════════════════════════════════════════════
with tb_settings:
    st.markdown("### ⚙️ Clinic & Doctor Settings")
    cur = get_settings()
    ss1, ss2 = st.columns(2, gap="large")

    with ss1:
        st.markdown("#### 🏥 Clinic Information")
        nc = st.text_input("Clinic Name *", value=cur["clinic_name"], key="t_cn")
        nca = st.text_area("Clinic Address", value=cur["clinic_address"], key="t_ca", height=80,
                           placeholder="e.g. 23, Civil Lines, Near SBI Bank, Moradabad - 244001")

        st.markdown("#### 👨‍⚕️ Doctor Profile")
        nd = st.text_input("Doctor Full Name *", value=cur["doc_name"], key="t_dn",
                           placeholder="e.g. Dr. G.S. Gill")
        nd2 = st.text_input("Primary Degree(s) *", value=cur["doc_degree"], key="t_deg",
                            placeholder="e.g. MBBS, PGDCCP")
        ns = st.text_input("Specialty / Designation", value=cur["doc_subtitle"], key="t_ds",
                           placeholder="e.g. CARDIO-PHYSICIAN")
        nr = st.text_input("Registration Number", value=cur["doc_reg_no"], key="t_reg",
                           placeholder="DMC/R/12345")
        nc2 = st.text_input("Doctor Phone", value=cur["doc_phone"], key="t_dp", placeholder="9876543210")
        nc3 = st.text_input("Doctor Email", value=cur["doc_email"], key="t_de", placeholder="dr@clinic.com")

        if st.button("💾 Save All Settings", type="primary", key="saveset", use_container_width=True):
            doc_extra = st.session_state.get("t_eq", cur.get("doc_extra_quals", ""))
            save_settings({
                "clinic_name": nc, "doc_name": nd, "doc_subtitle": ns,
                "doc_degree": nd2, "doc_reg_no": nr, "doc_email": nc3,
                "doc_phone": nc2, "clinic_address": nca, "doc_extra_quals": doc_extra,
            })
            st.success("✅ Settings saved! Prescription PDF mein reflect hoga.")
            st.rerun()

    with ss2:
        st.markdown("#### 🎓 Additional Qualifications")
        st.caption("Extra degrees, fellowships — PDF header mein dikhenge.")
        doc_extra = st.text_area(
            "Additional Qualifications", value=cur["doc_extra_quals"],
            key="t_eq", height=180,
            placeholder="e.g.\nFellowship in Cardiology (AIIMS Delhi)\nCertificate in Diabetology (RSSDI)"
        )

        st.markdown("---")
        st.markdown("#### 👀 Prescription Header Preview")
        header_lines = [f"🏥 **{nc or cur['clinic_name']}**"]
        header_lines.append(f"👨‍⚕️ {nd or cur['doc_name']}")
        if nd2:
            header_lines.append(f"🎓 {nd2}")
        if ns:
            header_lines.append(f"🔬 {ns}")
        if doc_extra:
            for line in doc_extra.strip().split('\n'):
                if line.strip():
                    header_lines.append(f"   {line.strip()}")
        if nr:
            header_lines.append(f"📋 Reg. No: {nr}")
        if nc2:
            header_lines.append(f"📞 {nc2}")
        if nc3:
            header_lines.append(f"✉️ {nc3}")
        if nca:
            header_lines.append(f"📍 {nca.split(chr(10))[0]}")
        st.markdown(
            "<div style='background:var(--color-background-secondary);"
            "border:1px solid var(--color-border-secondary);border-radius:8px;"
            "padding:16px 20px;font-size:13px;line-height:1.8;'>"
            + "<br>".join(header_lines) + "</div>",
            unsafe_allow_html=True
        )

        st.markdown("---")
        st.markdown("#### 📑 My Templates")
        tcat = st.radio("Category:", ["Medicines (Rx)", "Labs"], horizontal=True, key="tcat")
        tdb = "Rx" if "Rx" in tcat else "Lab"
        tdict = get_templates(tdb)
        with st.container(border=True):
            ntn = st.text_input("Template Name", key="ntn")
            ntb = st.text_area("Content", height=80, key="ntb")
            if st.button("💾 Save Template", type="primary", key="ntsave"):
                if ntn and ntb:
                    save_template(tdb, ntn, ntb)
                    st.success(f"✅ '{ntn}' saved!")
                    st.rerun()
                else:
                    st.warning("Name aur content dono chahiye.")

        sel_e = st.selectbox("Edit/Delete:", ["-- Select --"] + list(tdict.keys()), key="sel_e")
        if sel_e != "-- Select --":
            etb = st.text_area("Edit:", value=tdict[sel_e], height=80, key=f"et_{sel_e}")
            ec1, ec2 = st.columns(2)
            if ec1.button("💾 Update", type="primary", key="etupd"):
                save_template(tdb, sel_e, etb)
                st.success("✅ Updated!")
                st.rerun()
            if ec2.button("🗑️ Delete", key="etdel"):
                delete_template(sel_e)
                st.warning("Deleted.")
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# TAB: RESEARCH (Chief Only)
# ══════════════════════════════════════════════════════════════════════════
if is_chief:
    with tb_research:
        from admin.research_agent import render_research_agent
        render_research_agent()
