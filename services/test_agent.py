"""Stage 4 agent - Validation & Testing.

Builds the test plan from the story and the generated SQL package, then runs
static validation checks against the artifacts (file presence, DDL structure,
naming, safety) and produces a coverage summary. All checks are deterministic
so re-runs are reproducible.
"""
from __future__ import annotations

from datetime import datetime, timezone

REQUIRED_SQL = [
    "create_database.sql",
    "create_schema.sql",
    "create_tables.sql",
    "create_views.sql",
    "procedures.sql",
    "tasks.sql",
    "validation_queries.sql",
    "deployment_guide.md",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _specs(story: dict, sql: dict) -> list:
    """The ordered test plan; each spec carries a deterministic check."""
    tasks = story.get("tasks") or []

    def files_present():
        missing = [f for f in REQUIRED_SQL if not sql.get(f, "").strip()]
        return (not missing, "all %d files present and non-empty" % len(REQUIRED_SQL) if not missing else "missing: %s" % ", ".join(missing))

    def db_statement():
        ok = "CREATE DATABASE" in sql.get("create_database.sql", "").upper()
        return (ok, "CREATE DATABASE found" if ok else "create_database.sql has no CREATE DATABASE")

    def schema_statement():
        ok = "CREATE SCHEMA" in sql.get("create_schema.sql", "").upper()
        return (ok, "CREATE SCHEMA found" if ok else "create_schema.sql has no CREATE SCHEMA")

    def tables_defined():
        count = sql.get("create_tables.sql", "").upper().count("CREATE TABLE")
        return (count == 4, "4 tables defined" if count == 4 else "%d tables defined (expected 4)" % count)

    def views_defined():
        count = sql.get("create_views.sql", "").upper().count("CREATE OR REPLACE VIEW")
        return (count == 2, "2 views defined" if count == 2 else "%d views defined (expected 2)" % count)

    def procedures_defined():
        ok = "CREATE OR REPLACE PROCEDURE" in sql.get("procedures.sql", "").upper()
        return (ok, "procedures present" if ok else "no CREATE PROCEDURE found")

    def task_seed_rows():
        inserts = sql.get("tasks.sql", "").upper().count("INSERT INTO")
        ok = inserts == len(tasks)
        return (ok, "%d inserts match %d story tasks" % (inserts, len(tasks)) if ok else "%d inserts vs %d story tasks" % (inserts, len(tasks)))

    def validation_queries_present():
        selects = sql.get("validation_queries.sql", "").upper().count("SELECT")
        return (selects >= 5, "%d validation SELECTs" % selects if selects >= 5 else "only %d validation SELECTs" % selects)

    def story_complete():
        problems = []
        for field, label in [("name", "name"), ("description", "description"), ("story_points", "story points")]:
            if not story.get(field):
                problems.append(label)
        if not story.get("acceptance_criteria"):
            problems.append("acceptance criteria")
        if not tasks:
            problems.append("tasks")
        return (not problems, "story complete" if not problems else "story missing: %s" % ", ".join(problems))

    def syntax_hygiene():
        problems = []
        for fname, content in sql.items():
            if not fname.endswith(".sql"):
                continue
            if content.count("(") != content.count(")"):
                problems.append("%s: unbalanced parentheses" % fname)
            if not content.strip().endswith(";"):
                problems.append("%s: does not end with ;" % fname)
        return (not problems, "parentheses balanced, statements terminated" if not problems else "; ".join(problems))

    def safety_gate():
        violations = []
        for fname, content in sql.items():
            if not fname.endswith(".sql"):
                continue
            upper = content.upper()
            for keyword in ("DROP TABLE", "DROP DATABASE", "TRUNCATE", "DELETE FROM"):
                if keyword in upper:
                    violations.append("%s: %s" % (fname, keyword))
        return (not violations, "no destructive statements" if not violations else "; ".join(violations))

    def rollback_documented():
        ok = "rollback" in sql.get("deployment_guide.md", "").lower()
        return (ok, "rollback plan documented" if ok else "deployment guide has no rollback plan")

    return [
        ("T01", "All deployment files present and non-empty", "Artifact", files_present),
        ("T02", "Database creation statement present", "DDL", db_statement),
        ("T03", "Schema creation statement present", "DDL", schema_statement),
        ("T04", "All four core tables defined", "DDL", tables_defined),
        ("T05", "Both reporting views defined", "DDL", views_defined),
        ("T06", "Stored procedures defined", "DDL", procedures_defined),
        ("T07", "Task seed rows match story tasks", "Data", task_seed_rows),
        ("T08", "Validation queries executable structure", "Data", validation_queries_present),
        ("T09", "Story completeness check", "Story", story_complete),
        ("T10", "SQL syntax hygiene (parens / terminators)", "Syntax", syntax_hygiene),
        ("T11", "Safety gate - no destructive statements", "Safety", safety_gate),
        ("T12", "Rollback plan documented", "Docs", rollback_documented),
    ]


def generate_tests(story: dict, sql: dict) -> list:
    """Test plan for display (no check functions inside)."""
    return [
        {"id": tid, "name": name, "category": category}
        for tid, name, category, _ in _specs(story, sql)
    ]


def run_tests(story: dict, sql: dict) -> dict:
    """Execute every planned check and return the results summary."""
    tests = []
    for tid, name, category, check in _specs(story, sql):
        ok, detail = check()
        tests.append({
            "id": tid,
            "name": name,
            "category": category,
            "status": "passed" if ok else "failed",
            "detail": detail,
        })
    passed = sum(1 for t in tests if t["status"] == "passed")
    total = len(tests)
    failed = total - passed
    coverage = round(passed / total * 100, 1) if total else 0.0
    return {
        "tests": tests,
        "passed": passed,
        "failed": failed,
        "total": total,
        "coverage": coverage,
        "executed_at": _now(),
    }


def build_report(project_name: str, results: dict) -> str:
    """Markdown test report for download."""
    lines = [
        "# Test Report - %s" % project_name,
        "",
        "Executed: %s" % results.get("executed_at", ""),
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        "| Total tests | %d |" % results["total"],
        "| Passed | %d |" % results["passed"],
        "| Failed | %d |" % results["failed"],
        "| Coverage | %s%% |" % results["coverage"],
        "",
        "## Results",
        "",
        "| ID | Test | Category | Status | Detail |",
        "| --- | --- | --- | --- | --- |",
    ]
    for t in results["tests"]:
        lines.append("| %s | %s | %s | %s | %s |" % (t["id"], t["name"], t["category"], t["status"].upper(), t["detail"]))
    return "\n".join(lines) + "\n"
