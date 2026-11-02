"""Stage 4 - Validation & Testing.

Runs the deterministic validation suite against the generated artifacts,
shows passed / failed tests and coverage %, and requires approval before the
release stage unlocks.
"""
from __future__ import annotations

import streamlit as st

from database import db
from services import test_agent


def render(project_id: int, project_name: str) -> None:
    story = db.load_stage_data(project_id, "jira", "story")
    sql_files = db.load_stage_data(project_id, "build", "sql") or {}
    if not sql_files:
        st.info("Approve the build in Stage 3 first.")
        return

    results = db.load_stage_data(project_id, "testing", "results")
    artifacts = db.get_artifacts_dir(project_id)
    report_path = artifacts / "test_report.md"

    if st.button("\u25b6 Run Tests", key="test_run", type="primary"):
        results = test_agent.run_tests(story or {}, sql_files)
        db.save_stage_data(project_id, "testing", "results", results)
        report = test_agent.build_report(project_name, results)
        report_path.write_text(report, encoding="utf-8")
        db.log_audit(
            project_id, "testing", "run",
            "Executed %d tests - %d passed, %d failed, coverage %s%%"
            % (results["total"], results["passed"], results["failed"], results["coverage"]),
        )
        st.rerun()

    if not results:
        st.info("Run the validation suite to review the test results.")
        return

    m1, m2, m3 = st.columns(3)
    m1.metric("Passed tests", results["passed"])
    m2.metric("Failed tests", results["failed"])
    m3.metric("Coverage %", "%s%%" % results["coverage"])
    st.caption("Executed %s (UTC)" % results.get("executed_at", ""))

    passed = [t for t in results["tests"] if t["status"] == "passed"]
    failed = [t for t in results["tests"] if t["status"] == "failed"]

    with st.expander("\u2705 Passed tests (%d)" % len(passed), expanded=True):
        for t in passed:
            st.markdown("- **%s** - %s (%s): %s" % (t["id"], t["name"], t["category"], t["detail"]))
    with st.expander("\u274c Failed tests (%d)" % len(failed), expanded=bool(failed)):
        if failed:
            for t in failed:
                st.markdown("- **%s** - %s (%s): %s" % (t["id"], t["name"], t["category"], t["detail"]))
        else:
            st.markdown("No failed tests.")

    if report_path.exists():
        st.download_button(
            "\U0001f4e5 Download Test Report",
            data=report_path.read_bytes(),
            file_name="test_report.md",
            mime="text/markdown",
            key="test_report_download",
        )

    if st.button("\u2713 Approve Testing", key="test_approve", type="primary"):
        db.approve_stage(project_id, "testing")
        st.rerun()
