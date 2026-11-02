"""Stage 1 - Requirements Analysis.

Upload or paste the MOM text, extract requirements into professional cards,
regenerate on demand and approve before the workflow continues.
"""
from __future__ import annotations

import streamlit as st

from database import db
from pages.common import card_grid
from services import requirement_agent

CARD_SECTIONS = [
    ("requirements", "Requirements"),
    ("scope", "Scope"),
    ("objectives", "Objectives"),
    ("risks", "Risks"),
    ("assumptions", "Assumptions"),
    ("dependencies", "Dependencies"),
    ("acceptance_criteria", "Acceptance Criteria"),
]


def render(project_id: int, project_name: str) -> None:
    analysis = db.load_stage_data(project_id, "requirements", "analysis") or {}
    mom = db.load_stage_data(project_id, "requirements", "mom_text") or {}

    uploaded = st.file_uploader(
        "Upload MOM document (PDF, DOCX or TXT)", type=["pdf", "docx", "txt"], key="mom_upload"
    )
    pasted = st.text_area(
        "...or paste the MOM text directly",
        height=160,
        key="mom_paste",
        placeholder="Paste the minutes of meeting here, then press Regenerate",
    )

    can_generate = uploaded is not None or bool(pasted.strip()) or bool(mom.get("text"))
    col_action, col_approve = st.columns([1, 1])

    with col_action:
        if st.button("\u21bb Regenerate", key="req_regenerate", disabled=not can_generate):
            if uploaded is not None:
                text = requirement_agent.extract_text(uploaded.name, uploaded.getvalue())
            elif pasted.strip():
                text = pasted
            else:
                text = mom["text"]
            result = requirement_agent.analyze(text)
            db.save_stage_data(project_id, "requirements", "mom_text", {"text": text[:20000]})
            db.save_stage_data(project_id, "requirements", "analysis", result)
            db.log_audit(project_id, "requirements", "regenerate", "Requirements extracted from MOM document")
            st.rerun()

    if analysis:
        st.markdown(
            card_grid([(label, analysis.get(key) or []) for key, label in CARD_SECTIONS]),
            unsafe_allow_html=True,
        )
    else:
        st.info(
            "Upload or paste the MOM text, then click **Regenerate** to extract requirements, "
            "scope, objectives, risks, assumptions, dependencies and acceptance criteria."
        )

    with col_approve:
        if st.button("\u2713 Approve Requirements", key="req_approve", type="primary", disabled=not analysis):
            db.approve_stage(project_id, "requirements")
            st.rerun()
