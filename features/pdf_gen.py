"""PDF Generator — Prescription PDF banata hai letterhead ke saath. FPDF use karta hai."""
import logging, base64, re
from fpdf import FPDF
from config import settings as settings

log = logging.getLogger(__name__)

def _url_encode(text: str) -> str:
    """Simple URL encoding — re se handle kiya, no external urllib."""
    return re.sub(r"[^\w\s\-.(),/':@]", lambda m: f"%{ord(m.group()):02X}", text).replace(" ", "%20")

class _RxPDF(FPDF):
    """Custom FPDF — letterhead header, dynamic page breaks, aur footer."""

    def header(self) -> None:  # Clinic letterhead — naam, address, phone, email centered
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 10, settings.CLINIC_NAME, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, f"{settings.CLINIC_ADDRESS}  |  {settings.CLINIC_PHONE}  |  {settings.CLINIC_EMAIL}",
                  align="C", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y() + 2, 200, self.get_y() + 2)
        self.ln(6)

    def footer(self) -> None:
        """Footer — clinic tagline aur next visit reminder."""
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"{settings.CLINIC_NAME} — Your Health, Our Priority  |  See follow-up date above", align="C")

    def _chk(self) -> None:
        """Page overflow check — content bahut ho to naya page."""
        if self.get_y() > 260:
            self.add_page()

    def _kv(self, label: str, value: str) -> None:
        """Key-value pair likhta hai with page break check."""
        self._chk()
        self.set_font("Helvetica", "B", 11)
        self.cell(35, 7, f"{label}:", new_x="END")
        self.set_font("Helvetica", "", 11)
        self.multi_cell(0, 7, str(value) if value else "—")
        self.ln(1)

    def _sec(self, title: str) -> None:
        """Section heading with underline."""
        self._chk(); self.ln(2)
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(2)

def render_pdf_generator(patient_data: dict, rx_data: dict) -> bytes | None:
    """Full prescription PDF generate karta hai — letterhead, patient info, drugs, footer sab."""
    try:
        pdf = _RxPDF()
        pdf.add_page()
        # ── Doctor info (right-aligned) ──
        doc = f"Dr. {rx_data.get('doctor_name', '')}"
        if rx_data.get("qualifications"):
            doc += f" ({rx_data['qualifications']})"
        if rx_data.get("extra_qualifications"):
            doc += f", {rx_data['extra_qualifications']}"
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, doc, align="R", new_x="LMARGIN", new_y="NEXT")
        reg = rx_data.get("registration_number", "")
        if reg:
            pdf.set_font("Helvetica", "", 9)
            pdf.cell(0, 5, f"Reg: {reg}", align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        # ── Patient details ──
        pdf._kv("Patient", patient_data.get("name", ""))
        pdf._kv("Age/Gender", f"{patient_data.get('age', '')}/{patient_data.get('gender', '')}")
        pdf._kv("Phone", patient_data.get("phone", ""))
        pdf._kv("Address", patient_data.get("address", ""))
        pdf._kv("Date", rx_data.get("date", ""))
        # ── Clinical content ──
        for title, key in [("Chief Complaints", "complaints"), ("Findings / Examination", "findings"),
                           ("Vitals", "vitals"), ("Investigations", "investigations"), ("Advice", "advice")]:
            pdf._sec(title)
            pdf._kv("", rx_data.get(key, ""))
        # ── Rx symbol + drug list ──
        pdf._sec("\u211e Prescription")
        drugs = rx_data.get("drugs", "")
        if drugs:
            pdf.set_font("Helvetica", "", 10)
            for line in drugs.split("\n"):
                if line.strip():
                    pdf._chk()
                    pdf.multi_cell(0, 6, f"  • {line.strip()}")
        pdf.ln(2)
        pdf._kv("Follow-up", rx_data.get("follow_up", ""))
        return bytes(pdf.output())
    except Exception as e:
        log.error("render_pdf_generator error: %s", e, exc_info=True)
        return None

def generate_pdf_base64(patient_data: dict, rx_data: dict) -> str:
    """PDF bytes ko base64 string mein convert karta hai — HTML embedding ke liye."""
    try:
        pdf_bytes = render_pdf_generator(patient_data, rx_data)
        if pdf_bytes:
            return base64.b64encode(pdf_bytes).decode("utf-8")
    except Exception as e:
        log.error("generate_pdf_base64 error: %s", e)
    return ""

def generate_whatsapp_link(patient_data: dict, rx_data: dict) -> str:
    """WhatsApp pre-filled message link — patient ko prescription share karo."""
    try:
        name = patient_data.get("name", "Patient")
        msg = (f"Namaste {name} ji! Your prescription is ready.\n"
               f"Dr. {rx_data.get('doctor_name', '')}\n"
               f"Follow-up: {rx_data.get('follow_up', 'N/A')}\n"
               f"Advice: {rx_data.get('advice', 'N/A')}\n\n— {settings.CLINIC_NAME}")
        phone = re.sub(r"[^\d]", "", str(patient_data.get("phone", "")))
        if len(phone) >= 10:
            return f"https://wa.me/{phone}?text={_url_encode(msg)}"
    except Exception as e:
        log.error("generate_whatsapp_link error: %s", e)
    return "https://wa.me/?text=" + _url_encode("Prescription ready. Please visit the clinic.")
