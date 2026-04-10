"""
batch_scan.py — Upload multiple prescription photos, AI reads them, doctor reviews.
Features: multi-file upload, camera capture, batch processing, pending queue, approve/edit/skip.
FIXED: Saves to pending even when AI vision fails. Shows clear error messages.
"""

import io
import time
import logging

import streamlit as st
from PIL import Image

from ai_engine.groq_client import call_groq_vision, parse_ai_json
from database.sqlite_client import (
    save_pending, get_pending, update_pending, finalize_pending, count_pending,
    get_settings,
)
from utils.helpers import image_to_b64, b64_to_image_html

log = logging.getLogger(__name__)


def render_batch_scan():
    """
    Render the Batch Scan Upload tab with Upload and Review sub-tabs.
    Upload: upload/camera multiple prescriptions → AI reads all
    Review: edit AI output → approve/save or skip
    """
    did = st.session_state.get("doctor_id", "chief")
    pending_count = count_pending(did)

    bt1, bt2 = st.tabs([f"📸 Upload New Batch", f"📋 Review Pending ({pending_count})"])

    # ══════════════════════════════════════════════════════════════════════
    # TAB 1: UPLOAD NEW BATCH
    # ══════════════════════════════════════════════════════════════════════
    with bt1:
        st.markdown("### 📸 Upload Handwritten Prescriptions")
        st.info("""
**How to use:**
1. Click camera below or upload photos from gallery
2. Select multiple prescription photos at once (up to 20)
3. Click **Process All Prescriptions** — AI reads all prescriptions
4. Go to **Review Pending** tab to approve, edit, and save each one
        """)

        # Check API key
        groq_key = get_settings().get("groq_api_key", "")
        if not groq_key:
            st.error("""
            ⚠️ **Groq API key not set!** AI will not be able to read prescriptions.
            Go to **Settings** tab and enter your Groq API key first.
            You can get a free key at https://console.groq.com
            """)

        # File uploader (multiple files)
        uploaded_files = st.file_uploader(
            "Upload prescription photos", type=['jpg', 'jpeg', 'png', 'webp', 'heic'],
            accept_multiple_files=True, key="batch_files",
            help="Select all prescription photos at once (max 20 recommended)"
        )

        # Camera capture (one by one)
        st.markdown("**OR use camera** (take photos one by one):")
        cam_key = "batch_cam_list"
        if cam_key not in st.session_state:
            st.session_state[cam_key] = []
        cc1, cc2 = st.columns(2)
        with cc1:
            cam_pic = st.camera_input("Take prescription photo", key="batch_cam")
            if cam_pic and st.button("➕ Add to batch", key="add_cam"):
                st.session_state[cam_key].append(cam_pic)
                st.rerun()
        with cc2:
            if st.session_state[cam_key]:
                st.success(f"✅ {len(st.session_state[cam_key])} camera photo(s) added")
                if st.button("🗑️ Clear camera photos", key="clear_cam"):
                    st.session_state[cam_key] = []
                    st.rerun()

        # Combine all files
        all_files = list(st.session_state.get(cam_key, []))
        if uploaded_files:
            all_files.extend(uploaded_files)

        # Preview thumbnails
        if all_files:
            st.markdown(f"**{len(all_files)} prescription(s) ready to process:**")
            thumb_cols = st.columns(min(len(all_files), 5))
            for i, f in enumerate(all_files[:5]):
                with thumb_cols[i]:
                    try:
                        st.image(Image.open(f), caption=f"#{i + 1}", use_container_width=True)
                    except Exception:
                        st.write(f"File #{i + 1}")
            if len(all_files) > 5:
                st.caption(f"...and {len(all_files) - 5} more")

            extra_context = st.text_input(
                "Optional context for AI:", key="batch_context",
                placeholder="e.g. 'These are all cardiac patients from morning OPD'"
            )

            # ── PROCESS ALL BUTTON ───────────────────────────────────
            if st.button("🚀 Process All Prescriptions", type="primary", use_container_width=True):
                progress_bar = st.progress(0)
                status_text = st.empty()
                processed = 0
                ai_failed = 0
                failed = 0
                BATCH_SIZE = 3  # Process 3 at a time to avoid rate limits
                total = len(all_files)

                for batch_start in range(0, total, BATCH_SIZE):
                    for j, f in enumerate(all_files[batch_start:batch_start + BATCH_SIZE]):
                        idx = batch_start + j
                        status_text.info(f"🔄 Processing {idx + 1}/{total}...")
                        progress_bar.progress(idx / total)
                        try:
                            # Open image and convert to base64 for storage
                            img = Image.open(f)
                            img_b64 = image_to_b64(img)

                            # Call Groq Vision to read prescription
                            ai_text = ""
                            data = {}
                            if groq_key:
                                try:
                                    ai_text = call_groq_vision(img, extra_context)
                                    data = parse_ai_json(ai_text) if ai_text else {}
                                except Exception as e:
                                    log.error("AI vision error for file %d: %s", idx, e)
                                    ai_failed += 1

                            # Build formatted Rx text
                            full_rx = ""
                            if data.get("diagnosis"):
                                full_rx += f"DIAGNOSIS: {data['diagnosis']}\n\n"
                            if data.get("medicines"):
                                full_rx += f"MEDICATIONS:\n{data['medicines']}\n\n"
                            if data.get("advice"):
                                full_rx += f"ADVICE:\n{data['advice']}\n"
                            if data.get("follow_up"):
                                full_rx += f"FOLLOW-UP: {data['follow_up']}\n"

                            # If AI didn't extract medicines, add a note for doctor
                            if not full_rx.strip():
                                full_rx = "[AI could not read this prescription. Please review the image and enter details manually.]"

                            # Save to pending queue — ALWAYS save, even if AI failed
                            saved = save_pending(
                                did, img_b64, ai_text,
                                data.get("patient_name", ""),
                                data.get("phone", ""),
                                data.get("vitals", ""),
                                data.get("fee", "0"),
                                data.get("complaints", ""),
                                full_rx,
                                data.get("investigations", ""),
                            )
                            if saved:
                                processed += 1
                            else:
                                failed += 1
                        except Exception as e:
                            log.error("Batch scan error for file %d: %s", idx, e)
                            failed += 1

                    # Rate limit protection: wait between batches
                    if batch_start + BATCH_SIZE < total:
                        time.sleep(1)

                progress_bar.progress(1.0)

                # Show result summary
                if failed > 0:
                    status_text.error(f"❌ {failed} failed to save. Check if database is working.")
                elif processed > 0 and ai_failed == 0:
                    status_text.success(f"✅ Done! All {processed} processed with AI.")
                elif processed > 0 and ai_failed > 0:
                    status_text.warning(
                        f"✅ {processed} saved to pending queue. "
                        f"⚠️ {ai_failed} had AI errors — you can manually enter details in Review tab."
                    )
                else:
                    status_text.error("❌ Nothing was processed. Check your Groq API key and try again.")

                if processed > 0:
                    st.success(
                        f"**{processed} prescription(s)** saved to Pending queue! "
                        f"Go to **Review Pending** tab to approve and save."
                    )
                    st.session_state[cam_key] = []
        else:
            st.info("No files selected. Upload photos or use camera above.")

    # ══════════════════════════════════════════════════════════════════════
    # TAB 2: REVIEW PENDING PRESCRIPTIONS
    # ══════════════════════════════════════════════════════════════════════
    with bt2:
        st.markdown("### 📋 Review Pending Prescriptions")
        pending = get_pending(did)

        # Force refresh button (useful if count was stale)
        rc1, rc2 = st.columns([3, 1])
        with rc2:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()

        if not pending:
            st.success("🎉 No pending prescriptions! Upload new batch from the other tab.")
        else:
            st.info(f"**{len(pending)} prescription(s)** waiting for your review.")

            for idx, rx in enumerate(pending):
                # Show patient name or "Manual Entry Required"
                display_name = rx['patient_name'] or '(enter name manually)'
                ai_failed_marker = ""
                if rx['medicines'] and "[AI could not read" in str(rx['medicines']):
                    display_name = "(Manual entry needed) — click to edit"
                    ai_failed_marker = " ⚠️"

                with st.expander(
                    f"📄 #{idx + 1} | {display_name}{ai_failed_marker} | "
                    f"{rx['uploaded_at']}",
                    expanded=(idx == 0)
                ):
                    col_img, col_edit = st.columns([1, 1.5], gap="large")
                    with col_img:
                        st.markdown("**📷 Original Image:**")
                        if rx.get("image_b64"):
                            st.markdown(b64_to_image_html(rx["image_b64"]), unsafe_allow_html=True)
                        else:
                            st.warning("Image not available")
                        with st.expander("🤖 Raw AI Output"):
                            st.text(rx.get("ai_extracted", "No data"))

                    with col_edit:
                        st.markdown("**✏️ Review & Edit:**")
                        pt_name = st.text_input("Patient Name *", value=rx["patient_name"], key=f"rname_{rx['id']}")
                        rc_1, rc_2 = st.columns(2)
                        phone = rc_1.text_input("Phone", value=rx["phone"], key=f"rphone_{rx['id']}")
                        fee = rc_2.text_input("Fee ₹", value=rx["fee"] or "300", key=f"rfee_{rx['id']}")
                        vitals = st.text_input("Vitals", value=rx["vitals"], key=f"rvitals_{rx['id']}")
                        complaints = st.text_area("Complaints", value=rx["complaints"], height=80, key=f"rcomp_{rx['id']}")
                        medicines = st.text_area("Medicines / Rx", value=rx["medicines"], height=150, key=f"rmed_{rx['id']}")
                        investigations = st.text_input("Investigations", value=rx["investigations"], key=f"rinv_{rx['id']}")

                        st.markdown("---")
                        ba1, ba2, ba3 = st.columns(3)
                        with ba1:
                            if st.button("✅ Approve & Save", key=f"approve_{rx['id']}", type="primary", use_container_width=True):
                                if not pt_name.strip():
                                    st.warning("Patient name required.")
                                else:
                                    finalize_pending(rx['id'], did, pt_name, phone, vitals, fee, complaints, medicines, investigations)
                                    st.success(f"✅ {pt_name} saved!")
                                    st.rerun()
                        with ba2:
                            if st.button("💾 Save Draft", key=f"draft_{rx['id']}", use_container_width=True):
                                update_pending(rx['id'], pt_name, phone, vitals, fee, complaints, medicines, investigations, "pending")
                                st.success("Draft saved!")
                                st.rerun()
                        with ba3:
                            if st.button("🗑️ Skip", key=f"skip_{rx['id']}", use_container_width=True):
                                update_pending(rx['id'], pt_name, phone, vitals, fee, complaints, medicines, investigations, "skipped")
                                st.warning("Skipped.")
                                st.rerun()
