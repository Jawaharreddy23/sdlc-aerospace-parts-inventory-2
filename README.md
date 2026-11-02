# SDLC Orchestration Platform

A local, agentic SDLC orchestration dashboard built with **Streamlit + Python + SQLite**, designed to run entirely from **VS Code** on localhost. It walks a delivery through five gated stages - Requirements Analysis, Jira Story, Build & Deploy, Validation & Testing, Release & Pull Request - with explicit user approval at every step.

## Quick start

```bash
# from the project root in VS Code terminal
cd sdlc_orchestrator
python -m venv .venv
.venv\Scripts\activate        # Windows (use `source .venv/bin/activate` on macOS/Linux)
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501. Create a project in the sidebar and start with Stage 1.

## Project structure

```
sdlc_orchestrator/
├── app.py                    # main dashboard: header, tracker, stage cards, gating
├── requirements.txt
├── .streamlit/config.toml   # dark theme
├── pages/
│   ├── common.py           # CSS, progress tracker, cards, pills
│   ├── requirements.py     # Stage 1 UI
│   ├── jira.py             # Stage 2 UI
│   ├── build.py            # Stage 3 UI (SQL package + ZIP)
│   ├── testing.py          # Stage 4 UI (tests + report)
│   └── release.py          # Stage 5 UI (release docs + package)
├── services/
│   ├── llm_client.py       # optional Databricks model service bridge
│   ├── requirement_agent.py # Stage 1 agent (MOM extraction)
│   ├── jira_agent.py       # Stage 2 agent (story generation)
│   ├── build_agent.py      # Stage 3 agent (SQL generation)
│   ├── test_agent.py       # Stage 4 agent (validation suite)
│   └── release_agent.py    # Stage 5 agent (release docs)
├── database/
│   └── db.py               # SQLite schema + workflow state machine
├── artifacts/                # generated SQL / ZIP / reports per project
└── logs/                     # reserved for future run logs
```

## Workflow rules enforced by the app

1. **User approval required at every stage** - nothing advances automatically.
2. **Next stage stays locked** until the previous one is approved (visual lock banner).
3. **Previous stages can be reopened** - reopening revokes downstream approvals (data is kept for review).
4. **State persists** across refreshes and restarts (SQLite: `database/sdlc_orchestrator.db`).
5. **Status history** (`status_history` table) and **audit log** (`audit_log` table) record every transition; both are visible in the sidebar.

## Stage-by-stage

| Stage | Input | Output | Buttons |
| --- | --- | --- | --- |
| 1 Requirements Analysis | MOM (PDF/DOCX/TXT) | requirements, scope, objectives, risks, assumptions, dependencies, acceptance criteria (card layout) | Regenerate, Approve Requirements |
| 2 Jira Story | approved requirements | story name, description, ACs, story points, tasks | Edit Story, Approve Story |
| 3 Build & Deploy | approved story | 7 SQL files + deployment guide | Preview SQL, Generate Package, Download SQL Package (ZIP, never auto-downloaded), Approve Build |
| 4 Validation & Testing | SQL artifacts | test cases, passed/failed lists, coverage %, test report | Run Tests, Download Test Report, Approve Testing |
| 5 Release & PR | all approved stages | release notes, deployment notes, PR description | Download Release Package, Approve Release |

The ZIP package (`project_artifacts.zip`) contains: `create_database.sql`, `create_schema.sql`, `create_tables.sql`, `create_views.sql`, `procedures.sql`, `tasks.sql`, `validation_queries.sql` and `deployment_guide.md`.

## Connection settings (tokens)

All credentials live in **`config.json`** next to `app.py` (never inside code, never inside the exe):

1. Copy `config.example.json` to `config.json`
2. Fill in:
   * `databricks_host` + `databricks_token` - enables AI generation (Settings > Developer > Access tokens)
   * `model_service` - defaults to `system.ai.gpt-5`
   * `jira_site` / `jira_email` / `jira_token` / `jira_project` - enables the Stage 2 **Create Story in Jira** button. API token: id.atlassian.com > Security > API tokens. An existing issue with the same summary is found, updated and reused instead of creating a duplicate
   * `jira_issue_type` - `Story` by default; automatically falls back to `Task` when the project has no Story type
   * `github_token` - personal access token with **repo** scope; enables Stage 3 **Push to GitHub** and Stage 5 PR creation. Artifacts are pushed to a branch `sdlc/<issue-key>` and the release stage opens a pull request from it
   * `github_repo` - optional; defaults to a per-project private repo `sdlc-<project-name>` (created automatically if missing)
3. `config.json` is git-ignored - never commit or share it

All integrations are optional: buttons for unconfigured services are replaced by hints, and the workflow always works in local/deterministic mode.

Environment variables (`DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `MODEL_SERVICE`) override the file when set. Without any credentials the app runs in deterministic mode.

## Enabling AI generation (Databricks)

By default every agent runs in **deterministic mode** (template/heuristic generation) so the app works offline. To make the agents truly AI-powered, fill in `config.json` (see above) or set the environment variables before starting:

```bash
# Windows (PowerShell)
$env:DATABRICKS_HOST = "https://<your-workspace>.cloud.databricks.com"
$env:DATABRICKS_TOKEN = "<your-pat>"          # Settings > Developer > Access tokens
$env:MODEL_SERVICE = "system.ai.gpt-5"         # optional, any model service you can EXECUTE
streamlit run app.py
```

The sidebar shows a green **LLM connected** badge when configured. If a call fails, agents automatically fall back to deterministic mode, so the workflow never breaks.

## Build the Windows .exe

Prerequisites (once): Windows with Python 3.10+ on PATH. Then:

```bat
cd sdlc_orchestrator
build_exe.bat
```

The script creates a throwaway venv, installs PyInstaller and builds `dist\SDLCOrchestrator.exe`. After it finishes:

1. Copy `dist\SDLCOrchestrator.exe` into the `sdlc_orchestrator` folder itself (next to `app.py`, `pages/`, `services/`, `database/`)
2. Copy `config.example.json` to `config.json` and fill in your tokens
3. Double-click `SDLCOrchestrator.exe` and open http://localhost:8501 - no Python needed to run it

Notes:

* Tokens are read from `config.json` at runtime, deliberately **not** compiled into the exe, so they can be rotated without rebuilding and the exe can be shared without secrets.
* Windows SmartScreen may warn on first launch of a fresh PyInstaller build (unsigned) - click *More info > Run anyway*.
* First launch of a `--onefile` exe is slow (self-extraction); keep the exe inside the project folder so it can find `app.py` and the SQLite database.

## Database schema (SQLite)

| Table | Purpose |
| --- | --- |
| projects | one row per project |
| stage_status | approval flag + timestamps per (project, stage) |
| stage_data | generated payloads per stage (JSON) - analysis, story, SQL, results, docs |
| status_history | every status transition (from, to, actor, time) |
| audit_log | every user/agent action for the audit trail |

## Migrating to Databricks Delta later

All persistence goes through `database/db.py`. To move to Delta / Unity Catalog:

1. Replace the functions in `db.py` with implementations backed by the Databricks SQL connector (`databricks-sql-connector`) writing to Delta tables.
2. Keep the same function signatures - nothing in `pages/` or `services/` needs to change.
3. Move artifact files to a UC Volume and return volume paths instead.

## Troubleshooting

* **Port already in use** - `streamlit run app.py --server.port 8502`
* **PDF/DOCX upload fails** - confirm `pypdf` and `python-docx` are installed in the active venv.
* **Stages show as locked** - expected: approve the previous stage first.
* **Reset everything** - stop Streamlit and delete `database/sdlc_orchestrator.db`.
