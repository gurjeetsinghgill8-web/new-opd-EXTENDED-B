"""Bharat AI OPD - Diagnostic Tool. Shows exactly what files are missing."""
import os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))

# ── Check all required files ──
FILES = [
    'config/settings.py',
    'config/__init__.py',
    'database/sqlite_client.py',
    'database/supabase_client.py',
    'database/sync_manager.py',
    'database/__init__.py',
    'ai_engine/groq_client.py',
    'ai_engine/prompts.py',
    'ai_engine/__init__.py',
    'features/login.py',
    'features/rx_form.py',
    'features/patient_search.py',
    'features/roster.py',
    'features/specialty_upgrade.py',
    'features/pdf_gen.py',
    'features/__init__.py',
    'admin/portal.py',
    'admin/__init__.py',
    'utils/helpers.py',
    'utils/__init__.py',
    'requirements.txt',
    'Procfile',
    '.streamlit/config.toml',
    '.gitignore',
]

import streamlit as st
st.set_page_config(page_title="OPD File Check", page_icon="🔍")

st.title("🔍 File Checker")
st.markdown("Checking all files...")

missing = []
found = []
for f in FILES:
    path = os.path.join(_HERE, f)
    if os.path.exists(path):
        found.append(f)
        st.markdown(f"✅ `{f}`")
    else:
        missing.append(f)
        st.markdown(f"❌ `{f}` — **MISSING!**")

st.markdown("---")
if missing:
    st.error(f"### {len(missing)} FILES MISSING!")
    st.markdown("**Ye files upload karo GitHub pe:**")
    for f in missing:
        st.code(f)
else:
    st.success("### All files found!")
    st.markdown("Ab original main.py wapas lagao.")
