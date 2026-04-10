"""Rx Form — Prescription creation with AI, voice, drug search aur progress tracking."""
import logging
from datetime import datetime

import streamlit as st
import config.settings as settings
import database.sqlite_client as db
import ai_engine.groq_client as ai
import ai_engine.prompts as prompts
import utils.helpers as helpers

log = logging.getLogger(__name__)
_INV = ["CBC", "RBS", "LFT", "RFT", "Lipid Profile", "X-Ray", "ECG", "USG", "Urine RE"]

def render_rx_form(doctor_role: str) -> None:
    """Prescription form — patient details, clinical fields, AI Rx, save."""
    st.subheader("📝 New Prescription")
    drugs_sel: list[str] = list(st.session_state.get("selected_drugs", []))
    col_l, col_r = st.columns(2)
    with col_l:
        name = st.text_input("Patient Name", value=st.session_state.get("_pf_name", ""))
        age = st.number_input("Age", 0, 120, value=st.session_state.get("_pf_age", 30))
        gender = st.selectbox("Gender", ["Male", "Female", "Other"],
                              index=["Male", "Female", "Other"].index(
                                  st.session_state.get("_pf_gender", "Male")))
        phone = st.text_input("Phone", value=st.session_state.get("_pf_phone", ""))
        address = st.text_area("Address", value=st.session_state.get("_pf_addr", ""))
        # Voice scribe — complaint record karke text mein convert
        if settings.FEATURE_FLAGS.get("voice_scribe"):
            audio = st.audio_input("🎙️ Record Complaints")
            if audio:
                try:
                    st.session_state["_voice_complaints"] = ai.transcribe_audio(audio)
                    st.success("Transcribed!")
                except Exception as e:
                    log.error("Voice scribe: %s", e); st.warning("Transcription failed.")

    # ── Right: Clinical fields ─────────────────────────────────────────────────
    with col_r:
        complaints = st.text_area("Complaints", value=st.session_state.get(
            "_pf_complaints", ""), height=80)
        findings = st.text_area("Findings", height=80)
        vitals = st.text_input("Vitals", placeholder="BP: /, Pulse: , Temp: F, SpO2: %, Weight: kg")
        advice = st.text_area("Advice / Instructions", height=60)
        follow_up = st.text_input("Follow-up", placeholder="e.g. 7 days")
        inv = st.multiselect("Investigations", _INV)

    # ── Drug autocomplete — typing se search, click se select ──────────────────
    st.markdown("#### 💊 Drug Search & Selection")
    dq = st.text_input("Search drug name (type 2+ chars)")
    if len(dq) >= 2:
        matches = db.search_drugs(dq)
        if matches:
            cols = st.columns(min(len(matches), 6))
            for i, m in enumerate(matches):
                pill = m.get("name", "")
                if cols[i % len(cols)].button(pill, key=f"dpill_{i}"):
                    if pill not in drugs_sel:
                        drugs_sel.append(pill)
                    st.session_state["selected_drugs"] = drugs_sel; st.rerun()
    if drugs_sel:
        st.markdown("**Selected:** " + " | ".join(drugs_sel))
        if st.button("❌ Clear drugs"):
            drugs_sel.clear(); st.session_state["selected_drugs"] = []; st.rerun()

    # ── AI Rx — LLM se prescription suggest karta hai ──────────────────────────
    st.text_area("AI Rx (editable)", height=100, key="ai_rx_box")
    if settings.FEATURE_FLAGS.get("ai_rx") and st.button("🤖 Generate AI Rx"):
        try:
            pdata = {"name": name, "age": age, "gender": gender,
                     "complaints": complaints, "findings": findings, "vitals": vitals}
            st.session_state["ai_rx_box"] = ai.call_llm(prompts.get_rx_prompt(pdata))
            st.rerun()
        except Exception as e:
            log.error("AI Rx: %s", e); st.error("AI generation failed.")

    # ── Progress banner — previous visits ke vitals compare ────────────────────
    if settings.FEATURE_FLAGS.get("vitals_banner") and st.session_state.get("current_patient"):
        try:
            banner = helpers.compare_progress(st.session_state["current_patient"])
            if banner:
                st.markdown("### 📊 Progress Banner")
                for metric, val, color in banner:
                    icon = {"green": "🟢", "red": "🔴", "gray": "⚪"}.get(color, "⚪")
                    st.markdown(f"{icon} **{metric}**: {val}")
        except Exception as e:
            log.error("Progress banner: %s", e)

    # Save & Preview
    col_s, col_p = st.columns(2)
    with col_s:
        if st.button("💾 Save Prescription", type="primary", use_container_width=True):
            try:
                pid = st.session_state.get("current_patient")
                p_data = {"name": name, "age": str(age), "gender": gender,
                          "phone": phone, "address": address}
                if not pid:
                    pid = db.insert_patient(p_data)
                    st.session_state["current_patient"] = pid
                else:
                    db.update_patient(pid, p_data)
                if pid:
                    db.insert_rx({"patient_id": pid, "doctor": doctor_role,
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "complaints": complaints, "findings": findings,
                        "vitals": vitals, "drugs": ", ".join(drugs_sel),
                        "investigations": ", ".join(inv), "advice": advice,
                        "follow_up": follow_up, "specialty": "General Medicine", "pdf_path": ""})
                    cnt = st.session_state.get("rx_count_today", 0) + 1
                    st.session_state["rx_count_today"] = cnt
                    st.toast(f"✅ Rx #{cnt} saved!"); st.rerun()
            except Exception as e:
                log.error("Save rx: %s", e); st.error("Save failed.")
    with col_p:
        if st.button("📄 Preview PDF", use_container_width=True):
            st.session_state["nav_page"] = "pdf_gen"; st.rerun()
    for k in ("_pf_name", "_pf_age", "_pf_gender", "_pf_phone", "_pf_addr", "_pf_complaints"):
        st.session_state.pop(k, None)
