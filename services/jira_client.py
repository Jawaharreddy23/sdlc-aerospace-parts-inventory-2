"""Jira client - creates (or reuses) a real story via the Jira REST API v3.

Credentials come from config.json:
    jira_site       e.g. https://yourcompany.atlassian.net
    jira_email       the Atlassian account email
    jira_token       API token (id.atlassian.com > Security > API tokens)
    jira_project     project key to file stories under (e.g. INC)
    jira_issue_type  'Story' by default; falls back to 'Task' when the
                     project template has no Story type

Quirks handled here:
    * /rest/api/3/search is decommissioned (410) - search uses
      /rest/api/3/search/jql instead
    * descriptions must be Atlassian Document Format (ADF), not text
    * summaries longer than 255 chars are rejected

Reuse policy: before creating, the client searches the project for an
existing issue with the exact same summary. If one exists it is updated
(reused) instead of duplicated.
"""
from __future__ import annotations

import base64

import requests

from services.app_config import config

TIMEOUT = 60


def _site() -> str:
    return (config().get("jira_site") or "").rstrip("/")


def _email() -> str:
    return config().get("jira_email") or ""


def _token() -> str:
    return config().get("jira_token") or ""


def configured() -> bool:
    return bool(_site() and _email() and _token())


def project_key() -> str:
    return (config().get("jira_project") or "INC").strip()


def issue_type() -> str:
    return (config().get("jira_issue_type") or "Story").strip()


def issue_url(key: str) -> str:
    return "%s/browse/%s" % (_site(), key)


def _request(method: str, path: str, payload=None):
    basic = base64.b64encode(("%s:%s" % (_email(), _token())).encode("utf-8")).decode("ascii")
    headers = {
        "Authorization": "Basic %s" % basic,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    return requests.request(method, _site() + path, headers=headers, json=payload, timeout=TIMEOUT)


def _adf(text: str) -> dict:
    """Convert plain text into a minimal ADF document (one paragraph per line)."""
    lines = (text or "").splitlines() or [""]
    paragraphs = [
        {"type": "paragraph", "content": [{"type": "text", "text": line}]}
        for line in lines
    ]
    return {"type": "doc", "version": 1, "content": paragraphs}


def find_issue(summary: str):
    """Return the key of an existing issue with this exact summary, else None."""
    escaped = summary[:250].replace("\\", "\\\\").replace('"', '\\"')
    jql = 'project = "%s" AND summary = "%s"' % (project_key(), escaped)
    resp = _request("POST", "/rest/api/3/search/jql", {"jql": jql, "fields": ["key", "summary"]})
    if resp.status_code != 200:
        return None
    for issue in resp.json().get("issues", []) or []:
        fields = issue.get("fields", {})
        if (fields.get("summary") or "")[:255] == summary[:255]:
            return issue.get("key")
    return None


def create_issue(summary: str, description: str) -> str:
    payload = {
        "fields": {
            "project": {"key": project_key()},
            "summary": summary[:255],
            "issuetype": {"name": issue_type()},
            "description": _adf(description),
        }
    }
    resp = _request("POST", "/rest/api/3/issue", payload)
    if resp.status_code not in (200, 201):
        detail = resp.text[:400].lower()
        if "issue type" in detail or "issuetype" in detail or "story" in detail:
            payload["fields"]["issuetype"] = {"name": "Task"}
            resp = _request("POST", "/rest/api/3/issue", payload)
    if resp.status_code not in (200, 201):
        raise RuntimeError("Jira create failed (HTTP %s): %s" % (resp.status_code, resp.text[:300]))
    return resp.json()["key"]


def update_issue(key: str, summary: str, description: str) -> None:
    payload = {
        "fields": {
            "summary": summary[:255],
            "description": _adf(description),
        }
    }
    resp = _request("PUT", "/rest/api/3/issue/%s" % key, payload)
    if resp.status_code not in (200, 204):
        raise RuntimeError("Jira update failed (HTTP %s): %s" % (resp.status_code, resp.text[:300]))


def publish_story(story: dict) -> dict:
    """Create the story in Jira, or reuse and update an existing one.

    Returns {key, url, reused} where reused=True means an existing issue with
    the same summary was found and updated instead of creating a duplicate.
    """
    summary = story.get("name", "")
    description = story.get("description", "")
    existing = find_issue(summary)
    if existing:
        update_issue(existing, summary, description)
        return {"key": existing, "url": issue_url(existing), "reused": True}
    key = create_issue(summary, description)
    return {"key": key, "url": issue_url(key), "reused": False}
