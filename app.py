"""SDLC Orchestration - main dashboard.

Enterprise-style dark dashboard: header, horizontal progress tracker and
expandable stage cards with a strict approval-gated workflow. All workflow
state persists in SQLite, so nothing is lost on refresh or restart.
"""
from __future__ import annotations

import html

import streamlit as st

from database import db
from pages import build as stage_build
from pages import jira as stage_jira
from pages import release as stage_release
from pages import requirements as stage_requirements
from pages import testing as stage_testing
from pages.common import CSS, status_pill, tracker_html
from services import llm_client

STAGE_MODULES = {
    "requirements": stage_requirements,
    "jira": stage_jira,
    "build": stage_build,
    "testing": stage_testing,
    "release": stage_release,
}
ICONS = {"completed": "\u2713", "in_progress": "\u27f3", "pending": "\u25cb"}


def dashboard() -> None:
    st.set_page_config(page_title="SDLC Orchestration", page_icon="\u2699\ufe0f", layout="wide")
    st.markdown("<style>%s</style>" % CSS, unsafe_allow_html=True)
    db.init_db()
    render_sidebar()

    project = current_project()
    if project is None:
        st.markdown(
            '<div class="hero">Create your first project from the sidebar to begin.<br>'
            "The workflow: Requirements Analysis \u2192 Jira Story \u2192 Build &amp; Deploy \u2192 "
            "Validation &amp; Testing \u2192 Release &amp; Pull Request.</div>",
            unsafe_allow_html=True,
        )
        return

    project_id = project["id"]
    statuses = db.derive_statuses(project_id)
    story = db.load_stage_data(project_id, "jira", "story") or {}

    render_header(project, statuses, story.get("key", "\u2014"))
    st.markdown(tracker_html(statuses, db.STAGES, db.STAGE_LABELS), unsafe_allow_html=True)

    for i, stage in enumerate(db.STAGES):
        render_stage_card(i, stage, project, statuses)

    if all(meta["approved"] for meta in statuses.values()):
        st.success("\U0001f389 Workflow complete - every stage is approved and released.")


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown('<div class="sidebar-brand">\u2699\ufe0f SDLC Orchestration</div>', unsafe_allow_html=True)

        with st.expander("\u2795 New project"):
            name = st.text_input("Project name", key="new_project_name")
            if st.button("Create Project", key="create_project", type="primary"):
                if name.strip():
                    pid = db.create_project(name.strip())
                    st.session_state.project_id = pid
                    db.log_audit(pid, None, "project_created", "Project '%s' created" % name.strip())
                    st.rerun()

        projects = db.list_projects()
        if projects:
            ids = [p["id"] for p in projects]
            names = {p["id"]: p["name"] for p in projects}
            current = st.session_state.get("project_id", ids[0])
            index = ids.index(current) if current in ids else 0
            selected = st.selectbox(
                "Active project", ids, index=index, format_func=lambda x: names[x], key="project_select"
            )
            st.session_state.project_id = selected
        else:
            st.caption("No projects yet - create one above.")

        if llm_client.llm_enabled():
            st.markdown(
                '<div class="llm-badge on">\u25cf LLM connected - %s</div>' % html.escape(llm_client.model_name()),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="llm-badge">\u25cf Deterministic mode - set DATABRICKS_HOST &amp; '
                "DATABRICKS_TOKEN to enable AI generation</div>",
                unsafe_allow_html=True,
            )

        pid = st.session_state.get("project_id")
        if pid:
            with st.expander("\U0001f5c2 Audit log"):
                entries = db.get_audit_log(pid, 30)
                if entries:
                    for e in reversed(entries):
                        st.markdown(
                            "- `%s` \u00b7 **%s** \u00b7 %s" % (e["logged_at"][:19], e["action"], e["details"])
                        )
                else:
                    st.caption("No activity yet.")

            with st.expander("\U0001f4c8 Status history"):
                history = db.get_status_history(pid)
                if history:
                    for h in history:
                        st.markdown(
                            "- `%s` \u00b7 %s: %s \u2192 %s"
                            % (
                                h["changed_at"][:19],
                                db.STAGE_LABELS.get(h["stage"], h["stage"]),
                                h["from_status"],
                                h["to_status"],
                            )
                        )
                else:
                    st.caption("No transitions yet.")


def current_project():
    pid = st.session_state.get("project_id")
    return db.get_project(pid) if pid is not None else None


def render_header(project: dict, statuses: dict, story_key: str) -> None:
    all_done = all(meta["approved"] for meta in statuses.values())
    overall = "completed" if all_done else "in_progress"
    st.markdown(
        '<div class="sdlc-header">'
        "<div><div class=\"title\">SDLC Orchestration</div>"
        '<div class="subtitle">%s \u00b7 workflow console</div></div>'
        '<div class="chips">'
        '<span class="chip">Project <b>%s</b></span>'
        '<span class="chip">Jira Story <b>%s</b></span>'
        '<span class="chip">Status %s</span>'
        "</div></div>"
        % (
            html.escape(project["name"]),
            html.escape(project["name"]),
            html.escape(str(story_key)),
            status_pill(overall),
        ),
        unsafe_allow_html=True,
    )


def render_stage_card(index: int, stage: str, project: dict, statuses: dict) -> None:
    meta = statuses[stage]
    unlocked = all(statuses[s]["approved"] for s in db.STAGES[:index])
    title = "%s  Stage %d \u00b7 %s" % (ICONS[meta["status"]], index + 1, db.STAGE_LABELS[stage])
    with st.expander(title, expanded=meta["status"] == "in_progress"):
        if not unlocked:
            st.markdown(
                '<div class="locked">\U0001f512 Locked - approve the previous stage to unlock this one.</div>',
                unsafe_allow_html=True,
            )
            return
        STAGE_MODULES[stage].render(project["id"], project["name"])
        if meta["approved"]:
            st.success("Stage approved \u2705 - reopen to make changes (downstream approvals will be revoked).")
            if st.button("\u21bb Reopen stage", key="reopen_%s" % stage):
                db.reopen_stage(project["id"], stage)
                st.rerun()


# Programmatic navigation keeps the single-dashboard layout and stops
# Streamlit from auto-discovering the stage modules in pages/ as routes.
page = st.navigation([st.Page(dashboard, title="Dashboard", icon="\U0001f680", default=True)])
page.run()
