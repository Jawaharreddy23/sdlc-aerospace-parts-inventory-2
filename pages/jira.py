"""Stage 2 - Jira Story Creation.

Generates the story from the approved requirements, lets the user edit it,
optionally creates the real story in Jira (reusing an existing issue with
the same summary instead of duplicating), and requires explicit approval
before the build stage unlocks.
"""
from __future__ import annotations

import streamlit as st

from database import db
from services import jira_agent, jira_client


def render(project_id: int, project_name: str) -> None:
    analysis = db.load_stage_data(project_id, "requirements", "analysis") or {}
    story = db.load_stage_data(project_id, "jira", "story")

    if st.button(
        "Generate Story" if not story else "\u21bb Regenerate Story",
        key="story_generate",
        disabled=not analysis,
        type="primary" if not story else "secondary",
    ):
        story = jira_agent.generate_story(project_name, analysis)
        story["key"] = "SDLC-%03d" % project_id
        db.save_stage_data(project_id, "jira", "story", story)
        db.log_audit(project_id, "jira", "generate", "Jira story generated from approved requirements")
        st.rerun()

    if not story:
        st.info("Approve the requirements in Stage 1, then generate the Jira story.")
        return

    m1, m2, m3 = st.columns(3)
    m1.metric("Story points", story.get("story_points", "-"))
    m2.metric("Tasks", len(story.get("tasks") or []))
    m3.metric("Acceptance criteria", len(story.get("acceptance_criteria") or []))

    if st.toggle("\u270e Edit Story", key="story_edit"):
        with st.form("story_edit_form"):
            name = st.text_input("Story name", value=story.get("name", ""))
            description = st.text_area("Description", value=story.get("description", ""), height=180)
            if st.form_submit_button("Save Story", type="primary"):
                story["name"] = name.strip() or story.get("name", "")
                story["description"] = description
                db.save_stage_data(project_id, "jira", "story", story)
                db.log_audit(project_id, "jira", "edit", "Story edited by user")
                st.rerun()
    else:
        with st.expander("\U0001f4cb %s - %s" % (story.get("key", ""), story.get("name", "")), expanded=True):
            st.markdown(story.get("description", ""))
            st.markdown("**Acceptance criteria**")
            for i, ac in enumerate(story.get("acceptance_criteria") or [], 1):
                st.markdown("%d. %s" % (i, ac))
            st.markdown("**Tasks**")
            for task in story.get("tasks") or []:
                st.markdown("- \u2610 %s" % task)

    st.markdown("---")
    if jira_client.configured():
        if story.get("jira_key"):
            st.success(
                "Published to Jira: [%s](%s)%s"
                % (
                    story["jira_key"],
                    story.get("jira_url", "#"),
                    " - reused an existing issue" if story.get("jira_reused") else "",
                )
            )
            if st.button("\U0001f504 Update in Jira", key="jira_repush"):
                try:
                    result = jira_client.publish_story(story)
                    story["jira_key"] = result["key"]
                    story["jira_url"] = result["url"]
                    story["jira_reused"] = result["reused"]
                    db.save_stage_data(project_id, "jira", "story", story)
                    db.log_audit(project_id, "jira", "jira_update", "Story updated in Jira as %s" % result["key"])
                    st.rerun()
                except Exception as exc:
                    st.error("Jira update failed: %s" % exc)
        else:
            if st.button("\U0001f4cb Create Story in Jira", key="jira_push", type="primary"):
                try:
                    result = jira_client.publish_story(story)
                    story["jira_key"] = result["key"]
                    story["jira_url"] = result["url"]
                    story["jira_reused"] = result["reused"]
                    db.save_stage_data(project_id, "jira", "story", story)
                    db.log_audit(
                        project_id, "jira", "jira_publish",
                        "Story published to Jira as %s%s"
                        % (result["key"], " (reused existing issue)" if result["reused"] else ""),
                    )
                    st.rerun()
                except Exception as exc:
                    st.error("Jira publish failed: %s" % exc)
    else:
        st.caption(
            "Add jira_site / jira_email / jira_token / jira_project to config.json "
            "to create a real story in Jira."
        )

    if st.button("\u2713 Approve Story", key="story_approve", type="primary"):
        db.approve_stage(project_id, "jira")
        st.rerun()
