"""Stage 2 agent - Jira Story Creation.

Turns the approved requirements into a Jira-ready story: name, description,
acceptance criteria, story points and a task breakdown. Uses the LLM when
configured, otherwise a deterministic estimator.
"""
from __future__ import annotations

import json
import re

from services import llm_client

FIBONACCI = [1, 2, 3, 5, 8, 13]


def _clamp_points(value) -> int:
    """Snap any number to the nearest Fibonacci story-point value."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 5
    return min(FIBONACCI, key=lambda f: abs(f - v))


def _points_for(count: int) -> int:
    if count <= 3:
        return 3
    if count <= 5:
        return 5
    if count <= 8:
        return 8
    return 13


def _usable(items) -> list:
    return [i for i in (items or []) if i and not str(i).startswith("No explicit")]


def heuristic_story(project_name: str, analysis: dict) -> dict:
    reqs = _usable(analysis.get("requirements"))[:6]
    acs = _usable(analysis.get("acceptance_criteria"))[:8]
    objectives = _usable(analysis.get("objectives"))
    scope = _usable(analysis.get("scope")) or [
        "In scope: features and outcomes described in the approved MOM."
    ]
    risks = _usable(analysis.get("risks")) or ["No risks captured in the MOM."]

    base = objectives[0] if objectives else (reqs[0] if reqs else project_name + " delivery")
    name = base.split(".")[0].strip()
    name = name[:1].upper() + name[1:90]

    if not acs:
        acs = [
            "Requirement '%s' is delivered and demonstrable." % r[:80] for r in reqs[:5]
        ] or ["The workflow completes end-to-end with all stage approvals."]

    lines = [
        "As the delivery team for **%s**, we want to deliver the outcomes captured "
        "in the approved requirements so that the business objectives are met." % project_name,
        "",
        "### Scope",
    ]
    lines += ["- %s" % s for s in scope[:6]]
    lines += ["", "### Objectives"]
    lines += ["- %s" % o for o in (objectives or ["Deliver the requirements approved in Stage 1."])[:5]]
    lines += ["", "### Risks considered"]
    lines += ["- %s" % r for r in risks[:5]]
    description = "\n".join(lines)

    tasks = ["Implement: %s" % r[:100] for r in reqs] or ["Implement the approved requirements"]
    tasks += [
        "Author the SQL deployment package",
        "Execute the validation test suite",
        "Publish release notes and raise the pull request",
    ]
    return {
        "name": name,
        "description": description,
        "acceptance_criteria": acs,
        "story_points": _points_for(len(acs)),
        "tasks": tasks,
    }


def _llm_story(project_name: str, analysis: dict) -> dict:
    system = (
        "You are an agile coach writing a single Jira story from approved "
        "requirements. Reply with JSON only, no prose, no markdown fences, "
        "with keys: name (string), description (markdown string), "
        "acceptance_criteria (list of strings), story_points (integer), "
        "tasks (list of strings)."
    )
    user = (
        "Project: %s\n\nApproved requirements JSON:\n%s"
        % (project_name, json.dumps(analysis, ensure_ascii=False)[:8000])
    )
    raw = llm_client.chat(system, user, temperature=0.2, max_tokens=2500)
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    data = json.loads(raw)

    fallback = heuristic_story(project_name, analysis)
    story = {
        "name": str(data.get("name") or "").strip() or fallback["name"],
        "description": str(data.get("description") or "").strip() or fallback["description"],
        "acceptance_criteria": [
            str(a).strip() for a in (data.get("acceptance_criteria") or []) if str(a).strip()
        ][:10] or fallback["acceptance_criteria"],
        "story_points": _clamp_points(data.get("story_points", 5)),
        "tasks": [
            str(t).strip() for t in (data.get("tasks") or []) if str(t).strip()
        ][:12] or fallback["tasks"],
    }
    return story


def generate_story(project_name: str, analysis: dict) -> dict:
    """Generate the Jira story: LLM first when configured, heuristic fallback."""
    if llm_client.llm_enabled():
        try:
            return _llm_story(project_name, analysis)
        except Exception:  # noqa: BLE001
            pass
    return heuristic_story(project_name, analysis)
