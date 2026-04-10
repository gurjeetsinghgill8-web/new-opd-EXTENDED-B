"""
research_agent.py — Clinical research and practice data analysis (Chief only).
Analyzes patient data patterns to answer research questions.
"""

import streamlit as st
from ai_engine.groq_client import call_groq
from ai_engine.prompts import research_prompt
from database.sqlite_client import get_patients_filter, get_starred, get_settings
from utils.helpers import clean_fee


def render_research_agent():
    """
    Render the Clinical Research Agent tab (Chief only).
    Features: Ask questions, quick analysis buttons, PDF export.
    """
    sett = get_settings()

    st.markdown("### 🧠 Clinical Research & Practice Analytics")
    st.caption("Ask questions about your practice data — AI analyzes patterns and gives insights.")

    # Question input
    rq1, rq2 = st.columns([3, 1])
    rq = rq1.text_input(
        "💬 Ask anything about your practice:", key="rq",
        placeholder="Most common diagnosis? Top drugs? Revenue trends? Patient demographics?"
    )
    run_r = rq2.button("🧠 Analyze", type="primary", key="runr")

    # Quick analysis buttons
    sc1, sc2, sc3 = st.columns(3)
    if sc1.button("📊 Disease Distribution"):
        rq = "What are the most common diseases/diagnoses in my practice? Give top 10 with percentages."
    if sc2.button("💊 Top Medications"):
        rq = "What are the top 10 most prescribed medications in my practice?"
    if sc3.button("💰 Revenue Summary"):
        rq = "Give me a complete revenue summary: total, average fee per patient, monthly trend, highest revenue day."

    if run_r and rq:
        all_p = get_patients_filter("All Time")
        if not all_p:
            st.warning("No patient data found. Start prescribing first!")
            return

        total_r = sum(clean_fee(p['fee']) for p in all_p)
        sample = "\n".join([
            f"[{p['date'][:10]}|{p.get('specialty', 'GP')}|Vitals:{p['vitals']}|Rx:{p['medicines'][:80]}|Fee:{p['fee']}]"
            for p in all_p[:150]
        ])
        starred = get_starred()
        star_s = "\n".join([
            f"- {s['specialty']} for {s['patient_name']}: {s.get('star_note', '')}"
            for s in starred[:15]
        ])

        with st.spinner(f"Analyzing {len(all_p)} patient records..."):
            resp = call_groq(
                [research_prompt(sett['doc_name'], len(all_p), total_r, sample, star_s, rq)],
                temp=0.2
            )
            if resp:
                st.success(f"✅ {len(all_p)} patients analyzed")
                st.markdown(resp)
                # PDF export
                from features.pdf_generator import make_cme_pdf
                rpdf = make_cme_pdf("Research Report", resp)
                st.download_button(
                    "📥 Download Research PDF", data=rpdf,
                    file_name="Research_Report.pdf", mime="application/pdf"
                )
            else:
                st.error("Analysis failed. Check Groq API key.")
