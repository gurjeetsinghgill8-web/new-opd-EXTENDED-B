"""
starred.py — Starred specialty comparison view.
Displays all saved starred specialty upgrades with side-by-side GP vs Specialist Rx.
"""

import streamlit as st
from database.sqlite_client import get_starred
from features.pdf_generator import make_rx_pdf


def render_starred():
    """Render the Starred tab showing all saved specialty comparisons."""
    st.markdown("### ⭐ Starred Specialty Comparisons")
    starred = get_starred()

    if not starred:
        st.info("Koi starred case nahi. Prescription generate karo → Specialty Upgrade → ⭐ Star dabao.")
        return

    for su in starred:
        with st.expander(
            f"⭐ {su['patient_name']} | {su['specialty']} | "
            f"{str(su['date'])[:10]} | {su.get('star_note', '')}"
        ):
            sc1, sc2 = st.columns(2)
            with sc1:
                st.markdown("**🟦 Original GP Rx:**")
                st.text_area("", value=su['original_rx'], height=260,
                             key=f"so_{su['id']}", disabled=True)
            with sc2:
                st.markdown(f"**🟩 {su['specialty']}:**")
                st.text_area("", value=su['upgraded_rx'], height=260,
                             key=f"su_{su['id']}", disabled=True)

            if su.get('evidence'):
                st.info(f"📚 Evidence: {su['evidence']}")

            spdf = make_rx_pdf(
                su['patient_name'], su.get('vitals', ''),
                f"=== GP Rx ===\n{su['original_rx']}\n\n=== {su['specialty']} ===\n{su['upgraded_rx']}",
                specialty_label=su['specialty']
            )
            st.download_button(
                "📥 Download PDF", data=spdf,
                file_name=f"Star_{su['patient_name']}_{su['specialty'][:10]}.pdf",
                mime="application/pdf", key=f"sdl_{su['id']}"
            )
