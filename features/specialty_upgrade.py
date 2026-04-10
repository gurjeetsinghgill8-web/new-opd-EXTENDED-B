"""Specialty Upgrade — Jab symptoms complex ho to AI suggest karta hai kis specialty refer karna hai."""
import logging, json, re
import streamlit as st
from config import settings as settings
from database import sqlite_client as db
from ai_engine import groq_client as ai
from ai_engine import prompts as prompts

log = logging.getLogger(__name__)


def _parse_ai_response(text: str) -> dict:
    """AI response se JSON structure extract karta hai — markdown code block ya raw JSON dono handle."""
    try:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        stripped = text.strip()
        if stripped.startswith("{"):
            return json.loads(stripped)
    except json.JSONDecodeError:
        log.warning("JSON parse fail, plain text fallback use hoga.")
    return {"recommended_specialty": "Unclear", "urgency": "medium",
            "reasoning": text[:500], "investigations_needed": "N/A",
            "interim_management": "Await specialist review."}


def _urgency_badge(urgency: str) -> str:
    """Urgency level ke hisaab se emoji color badge return karta hai."""
    u = urgency.lower()
    if u in ("high", "urgent", "emergency"):
        return "🔴"
    if u in ("moderate", "medium"):
        return "🟡"
    return "🟢"


def _show_result(r: dict) -> None:
    """Single specialty analysis result card display karta hai."""
    st.markdown(f"### {r.get('specialty', '?')}")
    badge = _urgency_badge(r.get("urgency", "low"))
    st.markdown(f"**Urgency:** {badge} {r.get('urgency', 'N/A').title()}")
    st.markdown(f"**Recommended:** {r.get('recommended_specialty', 'N/A')}")
    st.write(r.get("reasoning", "N/A"))
    st.caption(f"**Investigations:** {r.get('investigations_needed', 'N/A')}")
    st.caption(f"**Interim Mgmt:** {r.get('interim_management', 'N/A')}")


def render_specialty_upgrade() -> None:
    """Multi-specialty AI comparison tool — complaints daalo, AI bataayega kahan refer karna hai."""
    try:
        st.subheader("🔬 Specialty Upgrade & Referral Advisor")
        complaints = st.text_area("Patient Complaints / Symptoms", height=100, key="su_complaints")
        current = st.selectbox("Current Specialty", settings.SPECIALTIES, key="su_current")
        custom = st.text_input("Or type a custom specialty name", key="su_custom")
        targets = st.multiselect("Compare with Specialties", settings.SPECIALTIES, key="su_targets")

        # Custom specialty override ya addition
        if custom.strip():
            all_targets = list(targets)
            if custom.strip() not in all_targets:
                all_targets.append(custom.strip())
        else:
            all_targets = list(targets)
        if not all_targets:
            st.warning("Kam se kam ek target specialty select karein.")
            return

        if st.button("🔍 Analyze", type="primary", key="su_analyze"):
            if not complaints.strip():
                st.warning("Complaints zaroor likhein."); return
            results: list[dict] = []
            # Har specialty ke liye AI call karo — comparison ke liye
            for spec in all_targets:
                try:
                    prompt = prompts.get_specialty_upgrade_prompt(complaints, current, spec)
                    response = ai.call_llm(prompt)
                    parsed = _parse_ai_response(response)
                    parsed["specialty"] = spec
                    results.append(parsed)
                except Exception as ex:
                    log.error("AI call failed for %s: %s", spec, ex)
                    results.append({"specialty": spec, "recommended_specialty": "Error",
                        "urgency": "low", "reasoning": str(ex),
                        "investigations_needed": "N/A", "interim_management": "Retry."})
            # Chat history mein store karo
            if "su_history" not in st.session_state:
                st.session_state.su_history: list[dict] = []
            st.session_state.su_history.append({"q": complaints, "results": results})

        # ── Results Display: side-by-side columns ──
        if "su_history" in st.session_state and st.session_state.su_history:
            latest = st.session_state.su_history[-1]["results"]
            if len(latest) == 1:
                _show_result(latest[0])
            else:
                cols = st.columns(min(len(latest), 3))
                for i, r in enumerate(latest):
                    with cols[i % len(cols)]:
                        _show_result(r)

            # Star / Save button — DB mein template store karo
            if st.button("⭐ Save as Template", key="su_save"):
                label = complaints[:60] if complaints else "Specialty Analysis"
                db.save_template(f"Specialty: {label}", json.dumps(latest))
                st.success("Template DB mein save ho gaya!")

        # ── History Expander: purane analyses dikhao ──
        if "su_history" in st.session_state and len(st.session_state.su_history) > 1:
            with st.expander("📜 Analysis History"):
                for idx, h in enumerate(reversed(st.session_state.su_history[:-1])):
                    st.markdown(f"**#{len(st.session_state.su_history) - idx}** — {h['q'][:80]}...")
    except Exception as e:
        log.error("render_specialty_upgrade error: %s", e, exc_info=True)
        st.error(f"Specialty upgrade mein error: {e}")
