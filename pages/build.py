"""Stage 3 - Build & Deploy.

Generates the SQL deployment artifacts, previews them, builds the ZIP
package (never downloaded automatically - only on button click), optionally
pushes the SQL package to GitHub, and requires approval before testing
unlocks.
"""
from __future__ import annotations

import io
import zipfile

import streamlit as st

from database import db
from services import build_agent, github_client


def render(project_id: int, project_name: str) -> None:
    story = db.load_stage_data(project_id, "jira", "story")
    analysis = db.load_stage_data(project_id, "requirements", "analysis") or {}
    if not story:
        st.info("Approve the Jira story in Stage 2 first.")
        return

    sql_files = db.load_stage_data(project_id, "build", "sql") or {}
    artifacts = db.get_artifacts_dir(project_id)
    sql_dir = artifacts / "sql"
    package = artifacts / "project_artifacts.zip"

    if st.button(
        "Generate SQL Artifacts" if not sql_files else "\u21bb Regenerate Artifacts",
        key="build_generate",
        type="primary" if not sql_files else "secondary",
    ):
        sql_files = build_agent.generate_sql(build_agent.slug(project_name), story, analysis)
        db.save_stage_data(project_id, "build", "sql", sql_files)
        sql_dir.mkdir(parents=True, exist_ok=True)
        for fname, content in sql_files.items():
            (sql_dir / fname).write_text(content, encoding="utf-8")
        db.log_audit(
            project_id, "build", "generate",
            "Generated %d SQL deployment artifacts" % len(sql_files),
        )
        st.rerun()

    if not sql_files:
        st.info("Generate the SQL deployment artifacts from the approved story.")
        return

    st.markdown("**Generated artifacts:** %s" % ", ".join(sorted(sql_files)))

    if st.toggle("\U0001f441 Preview SQL", key="build_preview"):
        for fname in sorted(sql_files):
            st.caption(fname)
            st.code(sql_files[fname], language="sql" if fname.endswith(".sql") else "markdown")

    col_pkg, col_dl = st.columns(2)
    with col_pkg:
        if st.button("\U0001f4e6 Generate Package", key="build_package"):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname, content in sql_files.items():
                    zf.writestr(fname, content)
            package.write_bytes(buffer.getvalue())
            db.log_audit(project_id, "build", "package", "SQL deployment package built (%d files)" % len(sql_files))
            st.rerun()

    with col_dl:
        if package.exists():
            st.download_button(
                "\U0001f4e5 Download SQL Package",
                data=package.read_bytes(),
                file_name="project_artifacts.zip",
                mime="application/zip",
                key="build_download",
            )
        else:
            st.caption("Generate the package to enable the download.")

    st.markdown("---")
    if github_client.configured():
        gh = db.load_stage_data(project_id, "build", "github") or {}
        if gh.get("url"):
            st.success("Pushed to GitHub: [%s](%s) (branch `%s`)" % (gh["repo"], gh["url"], gh["branch"]))
        if st.button("\U0001f680 Push to GitHub", key="build_github", type="secondary"):
            try:
                repo = github_client.ensure_repo(github_client.repo_name(project_name))
                branch = github_client.branch_name(story.get("jira_key") or story.get("key") or "SDLC")
                github_client.ensure_branch(repo, branch)
                files = {"sql/%s" % fname: content for fname, content in sql_files.items()}
                github_client.push_files(
                    repo, branch, files, "Build artifacts for %s" % story.get("key", "story")
                )
                db.save_stage_data(project_id, "build", "github", {
                    "repo": repo,
                    "branch": branch,
                    "url": "%s/tree/%s" % (github_client.repo_url(repo), branch),
                })
                db.log_audit(
                    project_id, "build", "github_push",
                    "SQL artifacts pushed to %s (branch %s)" % (repo, branch),
                )
                st.rerun()
            except Exception as exc:
                st.error("GitHub push failed: %s" % exc)
    else:
        st.caption("Add github_token to config.json to push the SQL package to GitHub.")

    if st.button("\u2713 Approve Build", key="build_approve", type="primary", disabled=not package.exists()):
        db.approve_stage(project_id, "build")
        st.rerun()
