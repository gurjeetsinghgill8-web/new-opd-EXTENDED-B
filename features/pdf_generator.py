"""
pdf_generator — Professional Indian prescription PDF and CME PDF generation.
Uses fpdf2 library. Generates letterhead with doctor/clinic info from settings.
"""

import re
import base64
import datetime
import logging

from fpdf import FPDF
from database.sqlite_client import get_settings
from utils.helpers import safe_str

log = logging.getLogger(__name__)


def make_rx_pdf(pt_name, vitals, rx_text, investigations="", specialty_label=""):
    sett = get_settings()
    pdf = FPDF()
    pdf.add_page()

    # ── Letterhead Background ─────────────────────────────────────────
    pdf.set_fill_color(235, 245, 255)
    pdf.rect(0, 0, 210, 54, 'F')
    pdf.set_draw_color(0, 51, 102)
    pdf.set_line_width(0.8)
    pdf.line(0, 54, 210, 54)
    pdf.set_line_width(0.2)

    # LEFT: Doctor Name
    pdf.set_xy(8, 4)
    pdf.set_font("Helvetica", 'B', 13)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(100, 7, safe_str(sett["doc_name"]), ln=False)

    # RIGHT: Clinic Name
    pdf.set_xy(108, 4)
    pdf.set_font("Helvetica", 'B', 12)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(97, 7, safe_str(sett["clinic_name"]), ln=False, align='R')

    # Degrees
    pdf.set_xy(8, 12)
    pdf.set_font("Helvetica", 'B', 9)
    pdf.set_text_color(30, 30, 120)
    pdf.cell(100, 5, safe_str(sett.get("doc_degree", "")), ln=False)

    # Address
    addr = sett.get("clinic_address", "")
    addr_lines = [l.strip() for l in addr.split("\n") if l.strip()] if addr else []
    pdf.set_xy(108, 12)
    pdf.set_font("Helvetica", '', 8)
    pdf.set_text_color(60, 60, 60)
    if addr_lines:
        pdf.cell(97, 5, safe_str(addr_lines[0]), ln=False, align='R')

    # Specialty
    pdf.set_xy(8, 18)
    pdf.set_font("Helvetica", 'I', 9)
    pdf.set_text_color(60, 60, 120)
    pdf.cell(100, 5, safe_str(sett.get("doc_subtitle", "")), ln=False)
    if len(addr_lines) > 1:
        pdf.set_xy(108, 18)
        pdf.set_font("Helvetica", '', 8)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(97, 5, safe_str(addr_lines[1]), ln=False, align='R')

    # Extra Qualifications
    extra = sett.get("doc_extra_quals", "")
    extra_lines = [l.strip() for l in extra.split("\n") if l.strip()] if extra else []
    pdf.set_font("Helvetica", '', 7)
    pdf.set_text_color(70, 70, 100)
    for i, eq in enumerate(extra_lines[:4]):
        pdf.set_xy(8, 24 + i * 4)
        pdf.cell(100, 4, safe_str(eq), ln=False)

    # Phone, Email, Reg No
    y_r = 24
    if sett.get("doc_phone"):
        pdf.set_xy(108, y_r)
        pdf.set_font("Helvetica", '', 8)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(97, 4, f"Ph: {safe_str(sett['doc_phone'])}", ln=False, align='R')
        y_r += 4
    if sett.get("doc_email"):
        pdf.set_xy(108, y_r)
        pdf.set_font("Helvetica", '', 8)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(97, 4, safe_str(sett["doc_email"]), ln=False, align='R')
        y_r += 4
    if sett.get("doc_reg_no"):
        pdf.set_xy(108, y_r)
        pdf.set_font("Helvetica", '', 8)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(97, 4, f"Reg: {safe_str(sett['doc_reg_no'])}", ln=False, align='R')

    # Specialty Consult Label
    if specialty_label:
        pdf.set_xy(8, 47)
        pdf.set_font("Helvetica", 'B', 8)
        pdf.set_text_color(139, 0, 0)
        pdf.cell(194, 5, f"* Specialty Consultation: {safe_str(specialty_label)} *", align='C', ln=False)

    # ── Patient Info Line ────────────────────────────────────────────
    pdf.set_xy(8, 57)
    pdf.set_font("Helvetica", 'B', 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(70, 6, f"Patient: {safe_str(pt_name)}", ln=False)
    pdf.cell(60, 6, f"Date: {datetime.date.today().strftime('%d-%b-%Y')}", ln=False)
    if vitals:
        pdf.set_font("Helvetica", '', 9)
        pdf.cell(65, 6, f"Vitals: {safe_str(vitals)}", ln=False)
    pdf.ln(6)
    y = pdf.get_y()
    pdf.line(8, y, 202, y)
    pdf.ln(3)

    # ── Prescription Body ────────────────────────────────────────────
    pdf.set_font("Helvetica", '', 10)
    body = re.sub(r'\*\*PHONE.*', '', rx_text, flags=re.IGNORECASE)
    body = safe_str(body.replace('**', '').replace('* ', '- '))
    pdf.multi_cell(0, 5.5, body)

    # ── Investigations Section ──────────────────────────────────────
    if investigations:
        pdf.ln(2)
        pdf.set_font("Helvetica", 'B', 10)
        y2 = pdf.get_y()
        pdf.line(8, y2, 202, y2)
        pdf.ln(2)
        pdf.cell(0, 6, "INVESTIGATIONS:", ln=True)
        pdf.set_font("Helvetica", '', 10)
        pdf.multi_cell(0, 5.5, safe_str(investigations))

    return pdf.output()


def make_cme_pdf(topic: str, content: str) -> bytes:
    sett = get_settings()
    pdf = FPDF()
    pdf.add_page()

    pdf.set_fill_color(240, 248, 255)
    pdf.rect(0, 0, 210, 30, 'F')
    pdf.set_font("Helvetica", 'B', 14)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 12, "CLINICAL GUIDELINES & PROTOCOLS", ln=True, align='C')
    pdf.set_font("Helvetica", 'I', 10)
    pdf.cell(0, 7, f"Topic: {safe_str(topic)} | {safe_str(sett['doc_name'])}", ln=True, align='C')

    pdf.ln(6)
    pdf.set_font("Helvetica", '', 11)
    pdf.set_text_color(0, 0, 0)
    clean_content = safe_str(content.replace('**', '').replace('* ', '- '))
    pdf.multi_cell(0, 6, clean_content)

    return pdf.output()


def show_pdf(pdf_bytes):
    import streamlit as st
    b64 = base64.b64encode(pdf_bytes).decode()
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}" '
        f'width="100%" height="460" style="border:1px solid #ddd;border-radius:8px;"></iframe>',
        unsafe_allow_html=True
    )
