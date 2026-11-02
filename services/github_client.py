"""GitHub client - pushes artifacts and opens pull requests via the REST API.

Credentials come from config.json:
    github_token  personal access token with 'repo' scope
    github_repo   optional; defaults to a per-project repo 'sdlc-<project>'
                  (created as private if it does not exist)

No git binary is required - everything goes through api.github.com. Artifacts
are pushed to a per-story branch (sdlc/<issue-key>) and the release stage
opens a pull request from that branch into the default branch.
"""
from __future__ import annotations

import base64
import re

import requests

from services.app_config import config

BASE = "https://api.github.com"
TIMEOUT = 60


def configured() -> bool:
    return bool((config().get("github_token") or "").strip())


def repo_name(project_name: str) -> str:
    """Configured repo, or a per-project default like 'sdlc-banking-modernization'."""
    configured_repo = (config().get("github_repo") or "").strip()
    if configured_repo:
        return configured_repo
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", project_name.strip().lower()).strip("-") or "project"
    return "sdlc-%s" % slug[:50]


def branch_name(story_key: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", str(story_key or "").strip().lower()).strip("-")
    return "sdlc/%s" % (slug or "workflow")


def _headers() -> dict:
    return {
        "Authorization": "Bearer %s" % (config().get("github_token") or "").strip(),
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _request(method: str, path: str, payload=None):
    return requests.request(method, BASE + path, headers=_headers(), json=payload, timeout=TIMEOUT)


def get_user() -> str:
    resp = _request("GET", "/user")
    if resp.status_code != 200:
        raise RuntimeError("GitHub auth failed (HTTP %s): %s" % (resp.status_code, resp.text[:200]))
    return resp.json()["login"]


def ensure_repo(name: str) -> str:
    """Return 'owner/name', creating a private repo when it does not exist."""
    owner = get_user()
    full = "%s/%s" % (owner, name)
    resp = _request("GET", "/repos/%s" % full)
    if resp.status_code == 200:
        return full
    if resp.status_code == 404:
        resp = _request("POST", "/user/repos", {"name": name, "private": True, "auto_init": True})
        if resp.status_code not in (200, 201):
            raise RuntimeError("GitHub repo creation failed (HTTP %s): %s" % (resp.status_code, resp.text[:300]))
        return full
    raise RuntimeError("GitHub repo lookup failed (HTTP %s): %s" % (resp.status_code, resp.text[:300]))


def repo_url(repo: str) -> str:
    return "https://github.com/%s" % repo


def default_branch(repo: str) -> str:
    resp = _request("GET", "/repos/%s" % repo)
    if resp.status_code != 200:
        raise RuntimeError("GitHub repo fetch failed (HTTP %s)" % resp.status_code)
    return resp.json()["default_branch"]


def head_sha(repo: str, branch: str) -> str:
    resp = _request("GET", "/repos/%s/git/ref/heads/%s" % (repo, branch))
    if resp.status_code != 200:
        raise RuntimeError("Branch '%s' not found (HTTP %s)" % (branch, resp.status_code))
    return resp.json()["object"]["sha"]


def ensure_branch(repo: str, branch: str) -> str:
    """Return the head sha of `branch`, creating it from the default branch when missing."""
    resp = _request("GET", "/repos/%s/git/ref/heads/%s" % (repo, branch))
    if resp.status_code == 200:
        return resp.json()["object"]["sha"]
    sha = head_sha(repo, default_branch(repo))
    resp = _request("POST", "/repos/%s/git/refs" % repo, {"ref": "refs/heads/%s" % branch, "sha": sha})
    if resp.status_code not in (200, 201):
        raise RuntimeError("GitHub branch creation failed (HTTP %s): %s" % (resp.status_code, resp.text[:300]))
    return sha


def put_file(repo: str, branch: str, path: str, content: str, message: str) -> str:
    """Create or update one file on a branch; returns the file's html_url."""
    resp = _request("GET", "/repos/%s/contents/%s?ref=%s" % (repo, path, branch))
    sha = resp.json().get("sha") if resp.status_code == 200 else None
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
    resp = _request("PUT", "/repos/%s/contents/%s" % (repo, path), payload)
    if resp.status_code not in (200, 201):
        raise RuntimeError("GitHub push failed for %s (HTTP %s): %s" % (path, resp.status_code, resp.text[:300]))
    return resp.json()["content"]["html_url"]


def push_files(repo: str, branch: str, files: dict, message: str) -> list:
    """files: {path: content}; each file is committed in order. Returns [(path, url)]."""
    results = []
    for path in sorted(files):
        url = put_file(repo, branch, path, files[path], "%s - %s" % (message, path))
        results.append((path, url))
    return results


def open_pull_request(repo: str, branch: str, title: str, body: str):
    """Open (or reuse) a PR from `branch` into the default branch.

    Returns (html_url, number).
    """
    owner = repo.split("/", 1)[0]
    resp = _request("GET", "/repos/%s/pulls?head=%s:%s&state=open" % (repo, owner, branch))
    if resp.status_code == 200 and resp.json():
        pr = resp.json()[0]
        return pr["html_url"], pr["number"]
    base = default_branch(repo)
    resp = _request(
        "POST",
        "/repos/%s/pulls" % repo,
        {"title": title[:255], "head": branch, "base": base, "body": body[:60000]},
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError("GitHub PR failed (HTTP %s): %s" % (resp.status_code, resp.text[:300]))
    data = resp.json()
    return data["html_url"], data["number"]
