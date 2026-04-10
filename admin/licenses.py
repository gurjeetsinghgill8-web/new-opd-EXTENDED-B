"""
licenses.py — Doctor license management UI.
Create, list, extend, delete doctor licenses.
"""

import re
import datetime
from datetime import timedelta

import streamlit as st
from database.sqlite_client import get_all_licenses, create_license, delete_license


def render_licenses_tab():
    """Render the Doctor Licenses management tab in admin panel."""
    st.markdown("### ➕ Create New Doctor License")
    with st.form("lic_form", clear_on_submit=True):
        lc1, lc2 = st.columns(2)
        l_did = lc1.text_input("Doctor ID (unique, no spaces) *", placeholder="dr_sharma")
        l_name = lc2.text_input("Doctor Full Name *")

        lc3, lc4 = st.columns(2)
        l_email = lc3.text_input("Email")
        l_phone = lc4.text_input("Phone")

        lc5, lc6 = st.columns(2)
        l_pin = lc5.text_input("Assign PIN * (4-8 digits)", placeholder="e.g. 7777")
        l_clinic = lc6.text_input("Clinic Name")

        lc7, lc8 = st.columns(2)
        l_spec = lc7.text_input("Specialty")
        l_exp = lc8.date_input(
            "Expiry Date",
            value=datetime.date.today() + timedelta(days=30),
            min_value=datetime.date.today()
        )
        l_notes = st.text_area("Notes", height=50)

        if st.form_submit_button("✅ Create License", type="primary"):
            if l_did and l_name and l_pin:
                l_did_clean = re.sub(r'[^a-z0-9_]', '', l_did.lower().replace(' ', '_'))
                if not l_did_clean:
                    st.error("Invalid Doctor ID. Use lowercase letters, numbers, underscores only.")
                else:
                    ok = create_license(l_did_clean, l_name, l_email or "", l_phone or "",
                                       l_pin, l_clinic or "", l_spec or "", l_exp, l_notes or "")
                    if ok:
                        st.success(
                            f"✅ License created! Doctor ID: `{l_did_clean}` | "
                            f"PIN: `{l_pin}` | Expires: {l_exp}"
                        )
                    else:
                        st.error("❌ Doctor ID or PIN already exists. Use different values.")
            else:
                st.warning("Doctor ID, Name, and PIN are required.")

    st.markdown("---")
    st.markdown("#### 📋 All Doctor Licenses")

    for lic in get_all_licenses():
        try:
            expiry = datetime.date.fromisoformat(str(lic["expiry_date"])[:10])
        except Exception:
            expiry = datetime.date.today()

        days_left = (expiry - datetime.date.today()).days
        if days_left >= 0:
            status = f"✅ Active ({days_left}d left)"
        else:
            status = f"❌ Expired ({abs(days_left)}d ago)"

        with st.expander(
            f"👨‍⚕️ {lic['doctor_name']} | ID:{lic['doctor_id']} | PIN:{lic['pin']} | {status}"
        ):
            st.write(f"📧 {lic['doctor_email']} | 📞 {lic['doctor_phone']} | 🏥 {lic['clinic_name']}")
            st.write(f"📅 Created: {lic['created_date']} | Expires: {lic['expiry_date']}")

            ec1, ec2, ec3 = st.columns(3)
            new_exp = ec1.date_input("Extend to:", value=expiry + timedelta(days=30), key=f"ext_{lic['id']}")
            if ec2.button("🔄 Extend", key=f"extb_{lic['id']}"):
                c = db._conn()
                c.execute("UPDATE licenses SET expiry_date=? WHERE id=?", (str(new_exp), lic['id']))
                c.commit()
                c.close()
                st.success(f"Extended to {new_exp}")
                st.rerun()
            if ec3.button("🗑️ Delete", key=f"delb_{lic['id']}"):
                delete_license(lic['id'])
                st.warning("License deleted.")
                st.rerun()
