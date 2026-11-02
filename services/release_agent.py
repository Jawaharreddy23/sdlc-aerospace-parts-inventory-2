"""Stage 5 agent - Release & Pull Request.

Produces the release notes, deployment notes and pull-request description
from the approved story, test results and requirements.
"""
from __future__ import annotations


def generate_release(project_name: str, story: dict, results: dict, analysis: dict) -> dict:
    story_name = story.get("name", project_name)
    story_key = story.get("key", "SDLC")
    acs = story.get("acceptance_criteria") or []
    tasks = story.get("tasks") or []
    reqs = (analysis.get("requirements") or [])[:10]
    passed = results.get("passed", 0)
    failed = results.get("failed", 0)
    total = results.get("total", 0)
    coverage = results.get("coverage", 0)

    release_notes = "\n".join(
        [
            "# Release Notes - %s" % story_key,
            "",
            "## %s" % story_name,
            "",
            "**Project:** %s  " % project_name,
            "**Story points:** %s  " % story.get("story_points", "-"),
            "**Release:** 1.0.0  ",
            "",
            "### What's included",
            "",
        ]
        + ["- %s" % r for r in reqs]
        + [
            "",
            "### Acceptance criteria",
            "",
        ]
        + ["%d. %s" % (i, ac) for i, ac in enumerate(acs, 1)]
        + [
            "",
            "### Test summary",
            "",
            "- Passed: %d / %d (coverage %s%%)" % (passed, total, coverage),
            "- Failed: %d" % failed,
            "",
            "### Known risks",
            "",
        ]
        + ["- %s" % r for r in (analysis.get("risks") or [])[:5]]
        + (["- None recorded."] if not (analysis.get("risks") or []) else [])
    )

    deployment_notes = "\n".join(
        [
            "# Deployment Notes - %s" % story_key,
            "",
            "## Execution order",
            "",
            "1. create_database.sql",
            "2. create_schema.sql",
            "3. create_tables.sql",
            "4. create_views.sql",
            "5. procedures.sql",
            "6. tasks.sql",
            "7. validation_queries.sql (all checks must pass)",
            "",
            "## Rollback",
            "",
            "Drop the application schema, then the database if required.",
            "All objects are created with IF NOT EXISTS / OR REPLACE, so a",
            "re-run of the package is safe.",
            "",
            "## Sign-off",
            "",
            "- Tests: %d/%d passed, coverage %s%%" % (passed, total, coverage),
            "- Story approved and released via the SDLC Orchestration Platform.",
        ]
    )

    pr_description = "\n".join(
        [
            "## Pull Request - %s: %s" % (story_key, story_name),
            "",
            "### Summary",
            "Delivers the approved requirements for **%s** as a full SQL" % project_name,
            "deployment package.",
            "",
            "### Changes",
            "",
        ]
        + ["- [ ] %s" % t for t in tasks]
        + [
            "",
            "### Test plan",
            "",
            "- [x] Validation suite executed: %d/%d passed (coverage %s%%)" % (passed, total, coverage),
            "- [ ] Reviewer confirms deployment in a staging environment.",
            "",
            "### Acceptance criteria",
            "",
        ]
        + ["- [ ] %s" % ac for ac in acs]
    )

    return {
        "release_notes": release_notes,
        "deployment_notes": deployment_notes,
        "pr_description": pr_description,
    }
