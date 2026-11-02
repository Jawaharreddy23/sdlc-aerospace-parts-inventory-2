"""Shared UI helpers and the enterprise dark-theme stylesheet.

Only pure presentation lives here: the tracker, status pills, cards and
the CSS injected into the dashboard. No workflow logic.
"""
from __future__ import annotations

import html

STAGE_ICONS = {"completed": "\u2713", "in_progress": "\u27f3", "pending": "\u25cb"}
STATUS_WORDS = {"completed": "Completed", "in_progress": "In Progress", "pending": "Pending"}

CSS = """
/* ---------------- app shell ---------------- */
div[data-testid="stAppViewContainer"] { background: #0d1117; }
section[data-testid="stSidebar"] { background: #10161f; border-right: 1px solid #263041; }

/* ---------------- header ---------------- */
.sdlc-header {
    background: linear-gradient(120deg, #0b1f3a 0%, #13274b 55%, #0d2a3e 100%);
    border: 1px solid #24486e; border-radius: 16px;
    padding: 20px 28px; display: flex; justify-content: space-between;
    align-items: center; flex-wrap: wrap; gap: 14px; margin-bottom: 6px;
}
.sdlc-header .title { font-size: 26px; font-weight: 800; color: #f0f6ff; letter-spacing: .4px; }
.sdlc-header .subtitle { color: #9db8dc; font-size: 14px; margin-top: 4px; }
.chips { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.chip {
    display: inline-flex; align-items: center; gap: 8px;
    background: #0e1c31; border: 1px solid #2b4d78; padding: 6px 14px;
    border-radius: 999px; font-size: 13px; color: #cfe0f5;
}
.chip b { color: #ffffff; font-weight: 700; }

/* ---------------- status pills ---------------- */
.status-pill {
    padding: 4px 12px; border-radius: 999px; font-size: 11px;
    font-weight: 700; text-transform: uppercase; letter-spacing: .8px;
}
.status-pill.completed { background: #123524; color: #3fb950; border: 1px solid #1f5c34; }
.status-pill.in-progress { background: #3a2b06; color: #f0b32e; border: 1px solid #6e5a10; }
.status-pill.pending { background: #21262d; color: #8b949e; border: 1px solid #30363d; }

/* ---------------- progress tracker ---------------- */
.tracker {
    display: flex; align-items: center; background: #0f141b;
    border: 1px solid #263041; border-radius: 16px;
    padding: 18px 26px; margin: 14px 0 22px 0;
}
.step { display: flex; flex-direction: column; align-items: center; gap: 6px; min-width: 128px; }
.step .ico {
    width: 38px; height: 38px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; font-weight: 800;
}
.step.completed .ico { background: #123524; color: #3fb950; border: 2px solid #238636; }
.step.in-progress .ico { background: #3a2b06; color: #f0b32e; border: 2px solid #9e6a03; animation: pulse 1.8s infinite; }
.step.pending .ico { background: #161b22; color: #6e7681; border: 2px solid #30363d; }
.step .lbl { font-size: 13px; font-weight: 600; color: #c9d4e0; text-align: center; }
.step .st { font-size: 10.5px; color: #7d8794; text-transform: uppercase; letter-spacing: .9px; }
.connector { flex: 1; height: 2px; margin: 0 6px 22px 6px; border-radius: 2px; background: #30363d; }
.connector.done { background: #238636; }
.connector.active { background: #9e6a03; }
@keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(240, 179, 46, .30); }
    50% { box-shadow: 0 0 0 9px rgba(240, 179, 46, 0); }
}

/* ---------------- stage cards ---------------- */
.card-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin: 10px 0; }
.card { background: #10161f; border: 1px solid #2a3547; border-radius: 12px; padding: 14px 16px; }
.card h4 { margin: 0 0 8px 0; color: #8ab4ff; font-size: 12px; text-transform: uppercase; letter-spacing: .9px; }
.card ul { margin: 0; padding-left: 16px; color: #c9d4e0; font-size: 13px; }
.card li { margin: 3px 0; }

/* ---------------- misc ---------------- */
.locked {
    background: #1a1206; border: 1px dashed #9e6a03; color: #f0b32e;
    padding: 10px 14px; border-radius: 10px; font-size: 13.5px;
}
.sidebar-brand { font-size: 17px; font-weight: 800; color: #f0f6ff; margin-bottom: 8px; }
.llm-badge {
    font-size: 12px; color: #8b949e; background: #161b22; border: 1px solid #30363d;
    padding: 6px 10px; border-radius: 8px; margin-top: 10px;
}
.llm-badge.on { color: #3fb950; border-color: #1f5c34; }
.hero {
    background: #10161f; border: 1px solid #2a3547; border-radius: 16px;
    padding: 60px 30px; text-align: center; color: #c9d4e0; font-size: 16px;
}
div[data-testid="stExpander"] { background: #10161f; border: 1px solid #2a3547; border-radius: 12px; }
.stButton > button { border-radius: 8px; font-weight: 600; }
"""


def tracker_html(statuses: dict, stages: list, labels: dict) -> str:
    """Horizontal progress tracker: done steps, pulsing current step,
    pending steps, coloured connectors."""
    parts = ['<div class="tracker">']
    for i, stage in enumerate(stages):
        meta = statuses[stage]
        s = meta["status"]
        parts.append(
            '<div class="step %s"><div class="ico">%s</div><div class="lbl">%s</div><div class="st">%s</div></div>'
            % (s, STAGE_ICONS[s], html.escape(labels[stage]), STATUS_WORDS[s])
        )
        if i < len(stages) - 1:
            conn = "done" if meta["approved"] else ("active" if s == "in_progress" else "")
            parts.append('<div class="connector %s"></div>' % conn)
    parts.append("</div>")
    return "".join(parts)


def status_pill(status: str) -> str:
    return '<span class="status-pill %s">%s</span>' % (status, STATUS_WORDS.get(status, status))


def card_grid(cards: list) -> str:
    """cards: list of (title, items) rendered as a two-column card grid."""
    blocks = []
    for title, items in cards:
        items = items if items else ["\u2014"]
        lis = "".join("<li>%s</li>" % html.escape(str(i)) for i in items)
        blocks.append(
            '<div class="card"><h4>%s</h4><ul>%s</ul></div>' % (html.escape(title), lis)
        )
    return '<div class="card-grid">%s</div>' % "".join(blocks)
