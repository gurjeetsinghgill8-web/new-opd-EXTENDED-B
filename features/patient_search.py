"""Patient Search — Name/phone se search, Google Sheet merge, Rx history, follow-up."""
import logging
from pathlib import Path

import streamlit as st

import config.settings as settings
import database.sqlite_client as db
import database.sync_manager as sync

log = logging.getLogger(__name__)


def render_patient_search() -> None:
    """Patient search page — local + Google Sheet results, Rx history, actions."""
    st.subheader("🔍 Patient Search")
    query = st.search_input("Search by name or phone number…")
    if not query:
        st.info("Type a name or phone number to search."); return

    # ── Local DB + Google Sheet dono se results lao ────────────────────────────
    local_results: list[dict] = db.search_patients(query)
    sheet_results: list[dict] = sync.fetch_google_sheet()

    # Local results ko source tag ke saath store karo
    all_rows: list[dict] = []
    for r in local_results:
        all_rows.append({**r, "source": "Local", "last_visit": r.get("updated_at", "")})
    # Google Sheet results — phone se deduplicate karo
    local_phones = {r.get("phone", "") for r in local_results}
    for r in sheet_results:
        if r.get("phone", "") not in local_phones and (
                query.lower() in r.get("name", "").lower() or query in r.get("phone", "")):
            all_rows.append({**r, "source": "Sheet", "last_visit": "N/A"})

    if not all_rows:
        st.warning("No patients found."); return

    # ── Dataframe display ──────────────────────────────────────────────────────
    st.markdown(f"**{len(all_rows)} results found**")
    df_data = [{"Name": r.get("name", ""), "Age": r.get("age", ""), "Gender": r.get("gender", ""),
                "Phone": r.get("phone", ""), "Last Visit": r.get("last_visit", ""),
                "Source": r.get("source", "")} for r in all_rows]
    event = st.dataframe(df_data, use_container_width=True, on_select="rerun",
                         selection_mode="single-row", hide_index=True)

    # ── Row selection ke baad details dikhao ───────────────────────────────────
    sel = event.selection.get("rows", [])
    if not sel:
        return
    row = all_rows[sel[0]]
    pid = row.get("id")
    st.markdown("---")
    st.markdown(f"### 📋 {row.get('name', 'N/A')}  ({row.get('gender', '')}, {row.get('age', '')})")
    st.caption(f"Phone: {row.get('phone', '')}  |  Address: {row.get('address', '')}")

    # ── Prescriptions history ──────────────────────────────────────────────────
    if pid:
        try:
            rx_list = db.get_rx_by_patient(pid)
        except Exception as e:
            log.error("Rx fetch: %s", e); rx_list = []
        if rx_list:
            st.markdown("#### 📜 Prescription History")
            for rx in rx_list:
                with st.expander(f"Rx #{rx.get('id', '')} — {rx.get('date', '')} by {rx.get('doctor', '')}"):
                    st.write(f"**Complaints:** {rx.get('complaints', '—')}")
                    st.write(f"**Findings:** {rx.get('findings', '—')}")
                    st.write(f"**Vitals:** {rx.get('vitals', '—')}")
                    st.write(f"**Drugs:** {rx.get('drugs', '—')}")
                    st.write(f"**Investigations:** {rx.get('investigations', '—')}")
                    st.write(f"**Advice:** {rx.get('advice', '—')}")
                    st.write(f"**Follow-up:** {rx.get('follow_up', '—')}")
                    # PDF download agar available hai
                    pdf_path = rx.get("pdf_path", "")
                    if pdf_path and Path(pdf_path).exists():
                        with open(pdf_path, "rb") as f:
                            st.download_button("📄 Download PDF", f, file_name=Path(pdf_path).name)
                    # Edit button — last prescription ko edit mode mein
                    if rx == rx_list[0] and st.button("✏️ Edit", key=f"edit_{rx.get('id', '')}"):
                        st.session_state["editing_rx"] = rx
                        st.session_state["nav_page"] = "rx_form"; st.rerun()
        else:
            st.info("No prescriptions found.")

    # ── Action buttons ────────────────────────────────────────────────────────
    col_f, col_r = st.columns(2)
    with col_f:
        # Follow-up button — form ko patient data se pre-fill karta hai
        if st.button("🔄 Follow-up", type="primary", use_container_width=True):
            st.session_state["_pf_name"] = row.get("name", "")
            st.session_state["_pf_age"] = int(row.get("age", 0) or 0)
            st.session_state["_pf_gender"] = row.get("gender", "Male")
            st.session_state["_pf_phone"] = row.get("phone", "")
            st.session_state["_pf_addr"] = row.get("address", "")
            st.session_state["current_patient"] = pid
            st.session_state["nav_page"] = "rx_form"; st.rerun()
    with col_r:
        # All PDFs for this patient
        if st.button("📂 All PDFs", use_container_width=True):
            if pid:
                try:
                    for rx in db.get_rx_by_patient(pid):
                        pp = rx.get("pdf_path", "")
                        if pp and Path(pp).exists():
                            with open(pp, "rb") as f:
                                st.download_button(f"📄 {Path(pp).name}", f,
                                                   file_name=Path(pp).name,
                                                   key=f"dl_{rx.get('id', '')}")
                except Exception as e:
                    log.error("PDF list: %s", e)
