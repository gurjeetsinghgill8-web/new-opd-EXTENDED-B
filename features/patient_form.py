"""
patient_form.py — Complete New Rx form with AI prescription generation.
Features: AI Rx, Drug autocomplete, Templates, Voice Scribe, Camera,
Quick Investigations, Specialty Upgrades, Drug Review, CME Study, WhatsApp share.
This is the HEART of the app — every major feature is accessible from here.
"""

import re
import datetime
import logging
import urllib.parse

import streamlit as st
from PIL import Image

from ai_engine.groq_client import call_groq, call_whisper
from ai_engine.prompts import (
    gp_prompt, specialty_prompt, specialty_chat_prompt,
    drug_review_prompt, cme_prompt, custom_cme_prompt, cme_chat_prompt,
    validate_rx,
)
from database.sqlite_client import (
    save_patient, search_patients, get_drug_suggestions,
    get_templates, save_template, save_upgrade, star_upgrade,
    get_settings,
)
from database.supabase_client import _supa_available
from features.pdf_generator import make_rx_pdf, show_pdf, make_cme_pdf
from config.settings import SPECIALTIES, QUICK_INVESTIGATIONS, DRUG_TYPES, DRUG_FREQUENCIES, DRUG_TIMINGS
from utils.helpers import compare_vitals, detect_conditions_from_complaints, extract_phone_from_rx

log = logging.getLogger(__name__)


def render_rx_form(uid="main"):
    """
    Render the full New Rx form with all features.
    uid: unique instance ID for session state keys (supports multiple forms).
    """
    # ── Session State Keys ────────────────────────────────────────────────
    RX_KEY = f"rx_{uid}"
    NOTE_KEY = f"notes_{uid}"
    UPG_KEY = f"upgrades_{uid}"
    SEL_KEY = f"sel_specs_{uid}"
    SHOW_UPG = f"show_upg_{uid}"

    if NOTE_KEY not in st.session_state:
        st.session_state[NOTE_KEY] = ""
    if "_note_override" in st.session_state:
        st.session_state[NOTE_KEY] = st.session_state.pop("_note_override")
    if UPG_KEY not in st.session_state:
        st.session_state[UPG_KEY] = {}
    if SEL_KEY not in st.session_state:
        st.session_state[SEL_KEY] = []
    if SHOW_UPG not in st.session_state:
        st.session_state[SHOW_UPG] = False

    is_fu = st.session_state.get("is_followup", False)
    past_vit = st.session_state.get("past_vitals", "")
    past_rx = st.session_state.get("past_rx", "")
    past_date = st.session_state.get("past_date", "")
    sett = get_settings()
    did = st.session_state.get("doctor_id", "chief")
    role = st.session_state.get("role", "chief")

    # ── Templates ────────────────────────────────────────────────────────
    rx_tmpl = get_templates("Rx")
    lab_tmpl = get_templates("Lab")
    if not rx_tmpl:
        rx_tmpl = {"HTN Standard": "1. Tab. Telmisartan 40mg - OD - After Breakfast - 30 Days\n2. Tab. Amlodipine 5mg - OD - After Breakfast - 30 Days"}
    if not lab_tmpl:
        lab_tmpl = {"Routine Cardiac": "ECG, Lipid Profile, FBS, HbA1c, RFT"}

    # ══════════════════════════════════════════════════════════════════════
    # LEFT COLUMN — Input Form
    # ══════════════════════════════════════════════════════════════════════
    cL, cR = st.columns([1, 1.2], gap="large")

    with cL:
        st.markdown("### 📝 Patient Details")

        def _pre(k, default=""):
            """Pop a pre-filled value from session state (for follow-up / edit)."""
            v = st.session_state.pop(f"pre_{k}", None)
            return v if v is not None else default

        pt_name = st.text_input("Patient Name *", value=_pre("name"), key=f"pname_{uid}")
        pc1, pc2, pc3 = st.columns([2, 2, 1])
        pt_phone = pc1.text_input("Phone", value=_pre("phone"), key=f"pphone_{uid}")
        pt_vitals = pc2.text_input("Vitals (BP/HR/Sug/Wt)", value=_pre("vitals"), key=f"pvit_{uid}")
        pt_fee = pc3.text_input("Fee ₹", value=_pre("fee", "300"), key=f"pfee_{uid}")

        # ── Follow-Up Banner ─────────────────────────────────────────
        if is_fu:
            st.info(f"🔄 Follow-Up | Past: {past_date} | AI diagnoses only from TODAY's notes.")
            if past_vit and pt_vitals:
                prog = compare_vitals(past_vit, pt_vitals, past_date)
                if prog:
                    if prog["color"] == "success":
                        st.success(prog["verdict"] + "\n\n" + "  \n".join(prog["lines"]))
                    elif prog["color"] == "error":
                        st.error(prog["verdict"] + "\n\n" + "  \n".join(prog["lines"]))
                    else:
                        st.warning(prog["verdict"] + "\n\n" + "  \n".join(prog["lines"]))
            elif past_vit:
                st.caption(f"📋 Past vitals: {past_vit} | Enter today's vitals to see progress.")

        # ── AI Condition Detection ───────────────────────────────────
        st.markdown("---")
        current_notes = st.session_state.get(NOTE_KEY, "")
        if pt_vitals or current_notes:
            detected = detect_conditions_from_complaints(current_notes, pt_vitals)
            if detected:
                st.markdown(f"**🧠 AI detected possible conditions:** {' | '.join(detected)}")

        # ── Smart Templates ──────────────────────────────────────────
        st.markdown("---")
        st.markdown("**📑 Smart Templates**")
        t1, t2 = st.columns(2)
        with t1:
            srx = st.selectbox("💊 Rx Template", ["-- Select --"] + list(rx_tmpl.keys()), key=f"srx_{uid}")
            if st.button("➕ Add", key=f"addrx_{uid}") and srx != "-- Select --":
                st.session_state["_note_override"] = st.session_state.get(NOTE_KEY, "") + "\n" + rx_tmpl[srx]
                st.rerun()
        with t2:
            slab = st.selectbox("🔬 Lab Template", ["-- Select --"] + list(lab_tmpl.keys()), key=f"slab_{uid}")
            if st.button("➕ Add", key=f"addlab_{uid}") and slab != "-- Select --":
                st.session_state["_note_override"] = st.session_state.get(NOTE_KEY, "") + "\n" + lab_tmpl[slab]
                st.rerun()

        # ── Voice / Audio Scribe ─────────────────────────────────────
        st.markdown("---")
        st.markdown("**🎙️ Voice / Audio Scribe**")
        aud = None
        if hasattr(st, "audio_input"):
            aud = st.audio_input("Record voice", key=f"arec_{uid}")
        uaud = st.file_uploader("Upload Audio", type=['wav', 'mp3', 'm4a', 'ogg'], key=f"aup_{uid}")
        if (aud or uaud) and st.button("🔄 Transcribe", key=f"trans_{uid}"):
            tgt = aud or uaud
            with st.spinner("Transcribing via Whisper AI..."):
                txt = call_whisper(tgt.getvalue(), getattr(tgt, 'name', 'audio.wav'))
                if txt:
                    cur = st.session_state.get(NOTE_KEY, "")
                    st.session_state["_note_override"] = cur + f"\n[Voice]: {txt}"
                    st.rerun()
                else:
                    st.warning("Transcription failed. Try again.")

        # ── Doctor's Clinical Notes ──────────────────────────────────
        st.markdown("**✍️ Doctor's Clinical Notes** *(Win+H for voice typing)*")
        dictation = st.text_area(
            "Clinical notes — complaints, findings, history...",
            key=NOTE_KEY, height=220,
            placeholder="e.g. 45M, chest pain since 3 days, BP 150/90, RBS 180, history of HTN..."
        )

        # ── Quick Investigations (one-click buttons) ─────────────────
        st.markdown("---")
        st.markdown("**🔬 Quick Investigations** *(click → notes mein add hoga)*")
        inv_cols = st.columns(4)
        for i, inv in enumerate(QUICK_INVESTIGATIONS):
            if inv_cols[i % 4].button(inv, key=f"inv_{inv}_{uid}", use_container_width=True):
                cur_notes = st.session_state.get(NOTE_KEY, "")
                if inv not in cur_notes:
                    st.session_state["_note_override"] = cur_notes + f"\nInv: {inv}"
                    st.rerun()

        INV_KEY = f"inv_{uid}"
        if INV_KEY not in st.session_state:
            st.session_state[INV_KEY] = ""
        investigations = st.text_input("Additional Investigations:", value=st.session_state[INV_KEY], key=f"inv_text_{uid}")
        st.session_state[INV_KEY] = investigations

        # ── Quick Drug Entry ─────────────────────────────────────────
        st.markdown("---")
        st.markdown("**💊 Quick Drug Entry**")
        drug_input = st.text_input("Drug Name", key=f"drug_inp_{uid}", placeholder="e.g. Metformin, Amlodipine...")
        if drug_input and len(drug_input) >= 2:
            suggestions = get_drug_suggestions(drug_input, did)
            if suggestions:
                st.caption(f"🕐 Previously used: **{' | '.join(suggestions[:5])}**")
                sug_cols = st.columns(min(len(suggestions[:4]), 4))
                for si, sug in enumerate(suggestions[:4]):
                    if sug_cols[si].button(sug, key=f"sug_{si}_{uid}", use_container_width=True):
                        parts = sug.split()
                        st.session_state[f"drug_inp_{uid}"] = parts[0] if parts else sug
                        st.rerun()

        dd1, dd2, dd3 = st.columns([1, 1, 1])
        drug_type = dd1.selectbox("Type", DRUG_TYPES, key=f"dtype_{uid}")
        drug_dose = dd2.text_input("Dose", key=f"ddose_{uid}", placeholder="500mg / 5ml")
        drug_name_mode = dd3.selectbox("Name Style", ["Generic only", "Brand only", "Generic + Brand"], key=f"dnamemode_{uid}")
        brand_name = ""
        if drug_name_mode in ["Brand only", "Generic + Brand"]:
            brand_name = st.text_input("Brand Name", key=f"dbrand_{uid}", placeholder="e.g. Glucophage")

        dd4, dd5, dd6 = st.columns(3)
        drug_freq = dd4.selectbox("Frequency", DRUG_FREQUENCIES, key=f"dfreq_{uid}")
        drug_timing = dd5.selectbox("Timing", DRUG_TIMINGS, key=f"dtime_{uid}")
        drug_days = dd6.text_input("Days", key=f"ddays_{uid}", placeholder="30 Days")

        if st.button("➕ Add This Drug to Notes", key=f"adddrug_{uid}", use_container_width=True):
            if drug_input.strip():
                if drug_name_mode == "Brand only":
                    full_name = brand_name.strip() if brand_name.strip() else drug_input.strip()
                elif drug_name_mode == "Generic + Brand":
                    full_name = drug_input.strip()
                    if brand_name.strip():
                        full_name += f" ({brand_name.strip()})"
                else:
                    full_name = drug_input.strip()
                existing_lines = [l for l in st.session_state.get(NOTE_KEY, "").split('\n') if re.match(r'^\d+\.', l.strip())]
                drug_num = len(existing_lines) + 1
                line = f"\n{drug_num}. {drug_type} {full_name} {drug_dose} - {drug_freq} - {drug_timing} - {drug_days}"
                st.session_state["_note_override"] = st.session_state.get(NOTE_KEY, "") + line
                st.rerun()

        # ── Camera / File Upload ─────────────────────────────────────
        st.markdown("---")
        with st.expander("📸 Camera / Upload Images & PDFs", expanded=False):
            CAM_KEY = f"cam_{uid}"
            if CAM_KEY not in st.session_state:
                st.session_state[CAM_KEY] = []
            cc1, cc2 = st.columns(2)
            with cc1:
                cam = st.camera_input("Take Photo", key=f"cpic_{uid}")
                if cam and st.button("➕ Add Photo", key=f"addcam_{uid}"):
                    st.session_state[CAM_KEY].append(cam)
                    st.rerun()
                if st.session_state[CAM_KEY]:
                    st.success(f"✅ {len(st.session_state[CAM_KEY])} photo(s)")
                    if st.button("🗑️ Clear", key=f"clrcam_{uid}"):
                        st.session_state[CAM_KEY] = []
                        st.rerun()
            with cc2:
                upf = st.file_uploader("Upload Files", type=['jpg', 'jpeg', 'png', 'pdf'], accept_multiple_files=True, key=f"fup_{uid}")

        all_media = list(st.session_state.get(CAM_KEY, []))
        if upf:
            all_media.extend(upf)

        # ── Build AI Content for Prescription Generation ─────────────
        past_ctx = ""
        if is_fu:
            past_ctx = f"\n--- PAST VISIT ({past_date}) ---\nPast Vitals: {past_vit}\nPast Rx: {past_rx}\n"
        prog_fmt = ""
        if is_fu:
            prog_fmt = "**IMPORTANT: Compare today's vitals with past visit and mention improvement/worsening in your diagnosis.**\n"

        ai_content = [gp_prompt(pt_name, pt_vitals, dictation, sett['doc_name'], past_ctx, prog_fmt)]
        for f in all_media:
            try:
                if hasattr(f, 'name') and f.name.lower().endswith('.pdf'):
                    try:
                        import fitz
                        doc = fitz.open(stream=f.read(), filetype="pdf")
                        for pn in range(min(len(doc), 3)):
                            pg = doc.load_page(pn)
                            pix = pg.get_pixmap()
                            ai_content.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
                    except Exception:
                        pass
                else:
                    ai_content.append(Image.open(f))
            except Exception:
                pass

        # ── GENERATE PRESCRIPTION BUTTON ─────────────────────────────
        if st.button("✨ Generate Prescription ➔", type="primary", use_container_width=True, key=f"gen_{uid}"):
            if not pt_name:
                st.warning("Patient name zaroori hai.")
            elif not (dictation or pt_vitals or all_media):
                st.warning("Notes, vitals ya image zaroori hai — AI ko kuch data chahiye.")
            else:
                with st.spinner("⚡ AI prescription bana raha hai..."):
                    res = call_groq(ai_content, temp=0.1)
                    if res:
                        # Validate Rx sections — retry if missing
                        is_valid, missing = validate_rx(res)
                        if not is_valid:
                            with st.spinner(f"⚠️ Retry ({', '.join(missing)} missing)..."):
                                res = call_groq(ai_content, temp=0.1)
                        if res:
                            st.session_state[RX_KEY] = res
                            st.session_state[UPG_KEY] = {}
                            st.session_state[SEL_KEY] = []
                            st.session_state["is_followup"] = False
                            st.rerun()
                    else:
                        st.error("AI generation failed. Check Groq API key in Settings.")

    # ══════════════════════════════════════════════════════════════════════
    # RIGHT COLUMN — Review, PDF, Actions, Specialty Upgrades
    # ══════════════════════════════════════════════════════════════════════
    with cR:
        if RX_KEY not in st.session_state:
            st.info("👈 Patient details bharo aur **Generate Prescription** dabao.")
            return

        st.markdown("### 📄 Review & Edit — GP Prescription")
        final_rx = st.text_area("Edit here:", value=st.session_state[RX_KEY], height=380, key=f"final_{uid}")

        # Auto-detect phone from Rx
        auto_ph = extract_phone_from_rx(final_rx)
        disp_ph = pt_phone if pt_phone else auto_ph
        if auto_ph and not pt_phone:
            st.success(f"📱 Auto-detected phone: **{auto_ph}**")

        # ── Save as Template ────────────────────────────────────────
        with st.expander("💾 Save as Template"):
            tc1, tc2, tc3 = st.columns([2, 1, 1])
            tname = tc1.text_input("Name", key=f"tname_{uid}")
            tc2.markdown("<br>", unsafe_allow_html=True)
            if tc2.button("💊 Rx", key=f"tsrx_{uid}") and tname:
                save_template("Rx", tname, final_rx)
                st.success("Saved!")
            tc3.markdown("<br>", unsafe_allow_html=True)
            if tc3.button("🔬 Lab", key=f"tslab_{uid}") and tname:
                save_template("Lab", tname, final_rx)
                st.success("Saved!")

        # ── Regenerate Button ───────────────────────────────────────
        if st.button("🔄 Regenerate", key=f"regen_{uid}"):
            with st.spinner("Regenerating..."):
                r = call_groq(ai_content, temp=0.1)
                if r:
                    st.session_state[RX_KEY] = r
                    st.rerun()

        # ── PDF Preview ─────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 👀 PDF Preview")
        pdf = make_rx_pdf(pt_name, pt_vitals, final_rx, investigations)
        show_pdf(pdf)

        # ── Action Buttons: Save, PDF Download, WhatsApp ─────────────
        st.markdown("---")
        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            if st.button("💾 Save Patient", use_container_width=True, key=f"savept_{uid}"):
                if not _supa_available():
                    st.warning("⚠️ **Cloud DB (Supabase) not connected.** Data saves locally + Google Sheet backup only.")
                existing = search_patients(pt_name)
                today_str = datetime.date.today().strftime("%Y-%m-%d")
                today_dupes = [p for p in existing if p["patient_name"].lower() == pt_name.lower() and str(p["date"])[:10] == today_str]
                if today_dupes:
                    st.warning(f"⚠️ {pt_name} aaj pehle se save hai ({len(today_dupes)} record).")
                    if st.button("✅ Haan, fir bhi save karein", key=f"force_save_{uid}"):
                        save_patient(pt_name, disp_ph, pt_vitals, pt_fee, dictation, final_rx, investigations, "General Physician", did)
                        st.success("✅ Patient saved!")
                        st.session_state.waiting_queue = [p for p in st.session_state.waiting_queue if p.get('name') != pt_name]
                else:
                    save_patient(pt_name, disp_ph, pt_vitals, pt_fee, dictation, final_rx, investigations, "General Physician", did)
                    st.success("✅ Patient saved!")
                    st.session_state.waiting_queue = [p for p in st.session_state.waiting_queue if p.get('name') != pt_name]
        with ac2:
            st.download_button("📄 PDF", data=pdf, file_name=f"{pt_name}_Rx.pdf",
                               mime="application/pdf", use_container_width=True, key=f"dlpdf_{uid}")
        with ac3:
            if disp_ph:
                msg = urllib.parse.quote(f"Namaste {pt_name},\nYour Rx:\n{final_rx}")
                st.link_button("💬 WhatsApp", f"https://wa.me/91{disp_ph}?text={msg}",
                               use_container_width=True)

        # ══════════════════════════════════════════════════════════════
        # SPECIALTY UPGRADE SECTION
        # ══════════════════════════════════════════════════════════════
        st.markdown("---")
        if st.button(
            "🔬 Specialty Upgrade Opinions ▼" if not st.session_state[SHOW_UPG] else "🔬 Specialty Upgrade ▲",
            use_container_width=True, key=f"togupg_{uid}"
        ):
            st.session_state[SHOW_UPG] = not st.session_state[SHOW_UPG]
            st.rerun()

        if st.session_state[SHOW_UPG]:
            st.markdown("#### Select Specialties (max 3) + Optional Custom")
            sc = st.columns(3)
            for i, sn in enumerate(SPECIALTIES):
                sel = sn in st.session_state[SEL_KEY]
                if sc[i % 3].button(f"{'✅ ' if sel else ''}{sn}", key=f"sb_{sn}_{uid}", use_container_width=True):
                    if sel:
                        st.session_state[SEL_KEY].remove(sn)
                    elif len(st.session_state[SEL_KEY]) < 3:
                        st.session_state[SEL_KEY].append(sn)
                    else:
                        st.warning("Maximum 3 specialties allowed")
                    st.rerun()

            custom_spec = st.text_input("➕ Custom Specialty:", key=f"cspec_{uid}")
            if custom_spec and f"🔬 {custom_spec}" not in st.session_state[SEL_KEY]:
                if st.button(f"Add '{custom_spec}'", key=f"addcs_{uid}"):
                    if len(st.session_state[SEL_KEY]) < 3:
                        st.session_state[SEL_KEY].append(f"🔬 {custom_spec}")
                        st.rerun()
                    else:
                        st.warning("Maximum 3 specialties allowed")

            if st.session_state[SEL_KEY]:
                st.success(f"Selected: {', '.join(st.session_state[SEL_KEY])}")
                if st.button("🚀 Generate Upgrades", type="primary", use_container_width=True, key=f"genupg_{uid}"):
                    for sn in st.session_state[SEL_KEY]:
                        is_cust = sn.startswith("🔬 ")
                        cname = sn[2:].strip() if is_cust else ""
                        sdata = SPECIALTIES.get(sn, {})
                        if is_cust:
                            with st.spinner(f"Fetching {cname} guidelines..."):
                                g = call_groq([f"List top 5 clinical guidelines for {cname} in India. Numbered list. ENGLISH only."], temp=0.1)
                                sdata = {
                                    "persona": f"Senior Specialist in {cname}",
                                    "guidelines": g or f"Standard {cname} guidelines",
                                    "focus": cname
                                }
                        with st.spinner(f"Consulting {sn}..."):
                            res = call_groq(
                                [specialty_prompt(pt_name, pt_vitals, final_rx, sn, sdata, cname if is_cust else "")],
                                temp=0.1
                            )
                            if res:
                                ev_m = re.search(r'\*\*EVIDENCE BASE\*\*(.*?)(\*\*|$)', res, re.DOTALL)
                                ev = ev_m.group(1).strip() if ev_m else ""
                                st.session_state[UPG_KEY][sn] = {"rx": res, "evidence": ev, "saved_id": None}
                    st.rerun()

            # ── Display Upgrade Results ──────────────────────────────
            for sn, ud in st.session_state[UPG_KEY].items():
                st.markdown("---")
                st.markdown(f"### {sn} vs GP Rx")
                cc1, cc2 = st.columns(2)
                with cc1:
                    st.markdown("**🟦 GP Prescription:**")
                    st.text_area("", value=st.session_state[RX_KEY], height=340,
                                 key=f"orig_{sn}_{uid}", disabled=True)
                with cc2:
                    st.markdown(f"**🟩 {sn} Upgraded:**")
                    ed = st.text_area("", value=ud["rx"], height=340, key=f"upg_{sn}_{uid}")
                    st.session_state[UPG_KEY][sn]["rx"] = ed
                if ud.get("evidence"):
                    st.info(f"📚 Evidence: {ud['evidence']}")

                # Follow-up Chat
                st.markdown(f"**💬 Ask {sn} a Follow-up Question:**")
                CHAT_KEY = f"chat_{sn}_{uid}"
                if CHAT_KEY not in st.session_state:
                    st.session_state[CHAT_KEY] = []
                chat_q = st.text_input(f"Your question to {sn}:", key=f"cq_{sn}_{uid}")
                if st.button(f"💬 Ask {sn}", key=f"askspec_{sn}_{uid}"):
                    if chat_q.strip():
                        with st.spinner(f"Consulting {sn}..."):
                            ctx = "\n".join([f"Q: {m['q']}\nA: {m['a']}" for m in st.session_state[CHAT_KEY][-3:]])
                            ans = call_groq(
                                [specialty_chat_prompt(sn, pt_name, pt_vitals, ud['rx'], ctx, chat_q)],
                                temp=0.1
                            )
                            if ans:
                                st.session_state[CHAT_KEY].append({"q": chat_q, "a": ans})
                                st.rerun()
                for msg in st.session_state[CHAT_KEY]:
                    st.markdown(f"**🩺 You:** {msg['q']}")
                    st.info(f"**{sn}:** {msg['a']}")

                # Upgrade Actions
                ua1, ua2, ua3, ua4 = st.columns(4)
                upg_pdf = make_rx_pdf(pt_name, pt_vitals, ud["rx"], specialty_label=sn)
                with ua1:
                    st.download_button("📄 PDF", data=upg_pdf,
                                       file_name=f"{pt_name}_{sn[:10]}_Rx.pdf",
                                       mime="application/pdf", key=f"dlupg_{sn}_{uid}", use_container_width=True)
                with ua2:
                    if st.button("📋 Use as Main Rx", key=f"usemain_{sn}_{uid}", use_container_width=True):
                        st.session_state[RX_KEY] = ud["rx"]
                        st.success("✅ Set as main Rx!")
                        st.rerun()
                with ua3:
                    snote = st.text_input("⭐ Note", key=f"snote_{sn}_{uid}", placeholder="Why star?")
                    if st.button("⭐ Star", key=f"star_{sn}_{uid}", use_container_width=True):
                        sid = save_upgrade(pt_name, pt_vitals, st.session_state[RX_KEY], sn, ud["rx"], ud.get("evidence", ""))
                        star_upgrade(sid, snote)
                        st.success("⭐ Starred!")
                with ua4:
                    if st.button("💾 Save", key=f"saveupg_{sn}_{uid}", use_container_width=True):
                        save_patient(pt_name, disp_ph, pt_vitals, pt_fee, dictation, ud["rx"], investigations, sn, did)
                        st.success("✅ Saved!")

        # ══════════════════════════════════════════════════════════════
        # DRUG REVIEW (Chief Only)
        # ══════════════════════════════════════════════════════════════
        if role == "chief":
            st.markdown("---")
            st.markdown("### 🛠️ Drug Review & Optimizer *(Chief Only)*")
            OPT_KEY = f"opt_{uid}"
            if st.button("🔍 Deep Drug Review", type="primary", key=f"optbtn_{uid}"):
                with st.spinner("Analyzing prescription..."):
                    res = call_groq([drug_review_prompt(pt_vitals, final_rx)], temp=0.1)
                    if res:
                        st.session_state[OPT_KEY] = res
                    else:
                        st.error("Drug review failed.")
            if OPT_KEY in st.session_state:
                st.markdown("---")
                st.markdown(
                    "<div style='background:var(--color-background-secondary);"
                    "border:0.5px solid var(--color-border-secondary);border-radius:12px;"
                    "padding:20px 28px;font-family:serif;line-height:1.9;font-size:15px;'>",
                    unsafe_allow_html=True
                )
                st.markdown(st.session_state[OPT_KEY])
                st.markdown("</div>", unsafe_allow_html=True)
                opt_pdf = make_cme_pdf("Drug Review & Optimization", st.session_state[OPT_KEY])
                st.download_button("📥 Download Drug Review PDF", data=opt_pdf,
                                   file_name=f"{pt_name}_DrugReview.pdf",
                                   mime="application/pdf", use_container_width=True, key=f"optdl_{uid}")

            # ══════════════════════════════════════════════════════════
            # CME STUDY (Chief Only)
            # ══════════════════════════════════════════════════════════
            st.markdown("---")
            st.markdown("### 📚 CME Study *(Chief Only)*")
            CME_KEY = f"cme_{uid}"
            CMET_KEY = f"cmet_{uid}"
            CME_CHAT_KEY = f"cme_chat_{uid}"
            if CME_CHAT_KEY not in st.session_state:
                st.session_state[CME_CHAT_KEY] = []

            if st.button("🔍 Find Study Topics", key=f"cmetopc_{uid}"):
                with st.spinner("Finding topics..."):
                    r = call_groq(
                        [f"Based on:\n{final_rx}\nSuggest 4 CME study topics. Numbered list only."],
                        temp=0.1
                    )
                    if r:
                        raw = [l.strip() for l in r.strip().split('\n') if l.strip() and l.strip()[0].isdigit()]
                        st.session_state[f"cme_topics_{uid}"] = raw or [
                            "1. Latest Hypertension Guidelines (NHB 2024)",
                            "2. Diabetes Management Update (RSSDI)",
                            "3. Lipid Management Targets",
                            "4. Antibiotic Stewardship in Indian OPD"
                        ]

            if f"cme_topics_{uid}" in st.session_state:
                cm1, cm2 = st.columns(2)
                with cm1:
                    st_t = st.selectbox("Topic:", st.session_state[f"cme_topics_{uid}"], key=f"cmesel_{uid}")
                    if st.button("📖 Read", key=f"cmeread_{uid}"):
                        with st.spinner("Fetching latest guidelines..."):
                            r = call_groq([cme_prompt(st_t)], temp=0.1)
                            if r:
                                st.session_state[CME_KEY] = r
                                st.session_state[CMET_KEY] = st_t
                                st.session_state[CME_CHAT_KEY] = []
                                st.rerun()
                with cm2:
                    cu_t = st.text_input("Custom topic:", key=f"cmecust_{uid}")
                    if st.button("📖 Read Custom", key=f"cmerc_{uid}"):
                        if cu_t:
                            with st.spinner("Fetching..."):
                                r = call_groq([custom_cme_prompt(cu_t)], temp=0.1)
                                if r:
                                    st.session_state[CME_KEY] = r
                                    st.session_state[CMET_KEY] = cu_t
                                    st.session_state[CME_CHAT_KEY] = []
                                    st.rerun()

            if CME_KEY in st.session_state:
                tn = st.session_state.get(CMET_KEY, "Guidelines")
                st.markdown("---")
                st.markdown(f"#### 📄 {tn} — Study Notes")
                st.markdown(
                    "<div style='background:var(--color-background-primary);"
                    "border:1px solid var(--color-border-secondary);border-left:4px solid #1565C0;"
                    "border-radius:8px;padding:24px 32px;font-size:15px;line-height:2.0;max-width:100%;'>",
                    unsafe_allow_html=True
                )
                st.markdown(st.session_state[CME_KEY])
                st.markdown("</div>", unsafe_allow_html=True)

                cpdf = make_cme_pdf(tn, st.session_state[CME_KEY])
                safe_topic = re.sub(r'[^A-Za-z0-9]', '_', tn)[:40]
                st.download_button("📥 Download Guidelines PDF", data=cpdf,
                                   file_name=f"CME_{safe_topic}.pdf",
                                   mime="application/pdf", use_container_width=True, key=f"cmedl_{uid}")

                # CME Follow-up Chat
                st.markdown(f"**💬 Ask more about '{tn}':**")
                cme_q = st.text_input("Your question:", key=f"cmeq_{uid}")
                if st.button("💬 Ask", key=f"cmeask_{uid}"):
                    if cme_q.strip():
                        with st.spinner("Fetching answer..."):
                            ctx = "\n".join([f"Q:{m['q']}\nA:{m['a']}" for m in st.session_state[CME_CHAT_KEY][-3:]])
                            ans = call_groq([cme_chat_prompt(tn, ctx, cme_q)], temp=0.1)
                            if ans:
                                st.session_state[CME_CHAT_KEY].append({"q": cme_q, "a": ans})
                                st.rerun()
                for msg in st.session_state[CME_CHAT_KEY]:
                    st.markdown(f"**🩺 Q:** {msg['q']}")
                    st.success(f"**A:** {msg['a']}")
