"""Stage 5 - Release & Pull Request.

Generates release notes, deployment notes and the PR description, offers a
single release package download, optionally pushes everything to GitHub
and opens a pull request, and completes the workflow on approval.
"""
from __future__ import annotations

import io
import zipfile

import streamlit as st

from database import db
from services import github_client, release_agent


def render(project_id: int, project_name: str) -> None:
    story = db.load_stage_data(project_id, "jira", "story")
    results = db.load_stage_data(project_id, "testing", "results")
    sql_files = db.load_stage_data(project_id, "build", "sql") or {}
    if not story or not results:
        st.info("Complete and approve the testing stage first.")
        return

    analysis = db.load_stage_data(project_id, "requirements", "analysis") or {}
    docs = db.load_stage_data(project_id, "release", "docs")
    if not docs:
        docs = release_agent.generate_release(project_name, story, results, analysis)
        db.save_stage_data(project_id, "release", "docs", docs)
        db.log_audit(project_id, "release", "generate", "Release documentation generated")
        st.rerun()

    tab_notes, tab_deploy, tab_pr = st.tabs(["\U0001f4dd Release Notes", "\U0001f6e0 Deployment Notes", "\U0001f4dc PR Description"])
    tab_notes.markdown(docs["release_notes"])
    tab_deploy.markdown(docs["deployment_notes"])
    tab_pr.markdown(docs["pr_description"])

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("release_notes.md", docs["release_notes"])
        zf.writestr("deployment_notes.md", docs["deployment_notes"])
        zf.writestr("PR_DESCRIPTION.md", docs["pr_description"])
        for fname, content in sorted(sql_files.items()):
            zf.writestr(fname, content)
    artifacts = db.get_artifacts_dir(project_id)
    (artifacts / "project_release.zip").write_bytes(buffer.getvalue())

    st.download_button(
        "\U0001f4e5 Download Release Package",
        data=buffer.getvalue(),
        file_name="project_release.zip",
        mime="application/zip",
        key="release_download",
    )

    st.markdown("---")
    if github_client.configured():
        gh = db.load_stage_data(project_id, "release", "github") or {}
        if gh.get("pr_url"):
            st.success("Pull request open: [%s](%s)" % (gh.get("pr", ""), gh["pr_url"]))
        if st.button("\U0001f680 Push Release to GitHub & Open PR", key="release_github", type="secondary"):
            try:
                repo = github_client.ensure_repo(github_client.repo_name(project_name))
                branch = github_client.branch_name(story.get("jira_key") or story.get("key") or "SDLC")
                github_client.ensure_branch(repo, branch)
                files = {
                    "release/release_notes.md": docs["release_notes"],
                    "release/deployment_notes.md": docs["deployment_notes"],
                    "release/PR_DESCRIPTION.md": docs["pr_description"],
                }
                # Include the SQL package too when the build stage did not push it.
                build_gh = db.load_stage_data(project_id, "build", "github") or {}
                if not build_gh.get("url"):
                    for fname, content in sorted(sql_files.items()):
                        files["sql/%s" % fname] = content
                github_client.push_files(
                    repo, branch, files, "Release artifacts for %s" % story.get("key", "story")
                )
                pr_url, pr_number = github_client.open_pull_request(
                    repo, branch,
                    "%s: %s" % (story.get("key", "SDLC"), story.get("name", "Release")),
                    docs["pr_description"],
                )
                db.save_stage_data(project_id, "release", "github", {
                    "repo": repo,
                    "branch": branch,
                    "pr": "#%d" % pr_number,
                    "pr_url": pr_url,
                })
                db.log_audit(
                    project_id, "release", "github_pr",
                    "Release pushed to %s and PR #%s opened" % (repo, pr_number),
                )
                st.rerun()
            except Exception as exc:
                st.error("GitHub release failed: %s" % exc)
    else:
        st.caption("Add github_token to config.json to push the release and open a pull request.")

    if st.button("\u2713 Approve Release", key="release_approve", type="primary"):
        db.approve_stage(project_id, "release")
        db.log_audit(project_id, "release", "released", "Workflow completed and release approved")
        st.balloons()
        st.rerun()
