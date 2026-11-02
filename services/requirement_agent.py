"""Stage 1 agent - Requirements Analysis.

Reads the uploaded MOM document (PDF / DOCX / TXT), extracts structured
requirements and, when a Databricks model service is configured, uses an LLM
for the extraction. Falls back to a deterministic section-heading heuristic
so the stage always produces a reviewable result.
"""
from __future__ import annotations

import io
import json
import re

from services import llm_client

SECTIONS = [
    "requirements",
    "scope",
    "objectives",
    "risks",
    "assumptions",
    "dependencies",
    "acceptance_criteria",
]

SECTION_LABELS = {
    "requirements": "Requirements",
    "scope": "Scope",
    "objectives": "Objectives",
    "risks": "Risks",
    "assumptions": "Assumptions",
    "dependencies": "Dependencies",
    "acceptance_criteria": "Acceptance Criteria",
}

ALIASES = {
    "requirements": "requirements",
    "requirements analysis": "requirements",
    "scope": "scope",
    "scope of work": "scope",
    "objectives": "objectives",
    "objective": "objectives",
    "risks": "risks",
    "risk": "risks",
    "assumptions": "assumptions",
    "assumption": "assumptions",
    "dependencies": "dependencies",
    "dependency": "dependencies",
    "acceptance criteria": "acceptance_criteria",
    "acceptance criterion": "acceptance_criteria",
    "ac": "acceptance_criteria",
}


# ---------------------------------------------------------------------------
# Document text extraction
# ---------------------------------------------------------------------------

def extract_text(filename: str, payload: bytes) -> str:
    """Return the plain text of an uploaded PDF, DOCX or TXT file."""
    suffix = filename.rsplit(".", 1)[-1].lower()
    if suffix == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(payload))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == "docx":
        import docx

        document = docx.Document(io.BytesIO(payload))
        parts = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts)
    return payload.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _clean(item: str) -> str:
    """Strip markdown bullets and leading numbering from a captured line."""
    item = item.strip()
    item = item.lstrip("-*\u2022\u2013\u2014> ")
    item = re.sub(r"^\d+[.)]\s*", "", item)
    return item.strip()


def heuristic_analysis(text: str) -> dict:
    """Split the MOM into sections by detecting known headings, then capture
    the lines that follow each heading as its items."""
    sections = {key: [] for key in SECTIONS}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        cleaned = line.strip("#*-\u2192>: ").strip()
        low = cleaned.lower()
        key = ALIASES.get(low)
        if key is None:
            for alias, target in ALIASES.items():
                if low.startswith(alias) and len(low) <= len(alias) + 3:
                    key = target
                    break
        if key is not None:
            current = key
            remainder = cleaned.split(":", 1)[-1].strip() if ":" in cleaned else ""
            if remainder:
                sections[current].append(_clean(remainder))
            continue
        if current is not None:
            item = _clean(cleaned)
            if item:
                sections[current].append(item)
    _apply_fallbacks(sections, text)
    return sections


def _apply_fallbacks(sections: dict, text: str) -> None:
    """If the document had no recognisable structure, synthesise a minimal
    baseline so the user always has something reviewable on screen."""
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 15]
    if not any(sections.values()) and lines:
        sections["objectives"] = [_clean(l)[:160] for l in lines[:3]]
        sections["requirements"] = [
            "Deliver " + l[0].lower() + l[1:140].rstrip(".") + "." for l in lines[:4]
        ]
        sections["scope"] = [
            "In scope: the features and outcomes described in this MOM.",
            "Out of scope: anything not explicitly listed as an objective.",
        ]
        sections["acceptance_criteria"] = [
            "Each requirement listed above is implemented and demonstrable.",
            "The deployment package passes the full validation test suite.",
        ]
    for key in SECTIONS:
        if not sections[key]:
            sections[key] = [
                "No explicit %s captured in the MOM - regenerate with a richer document."
                % SECTION_LABELS[key].lower()
            ]
        sections[key] = sections[key][:20]


def _llm_analysis(text: str) -> dict:
    system = (
        "You are a senior business analyst. You read minutes-of-meeting documents "
        "and extract structured requirements. Reply with JSON only, no prose, "
        "no markdown fences."
    )
    keys = ", ".join(SECTIONS)
    user = (
        "Extract the following sections from the MOM below. Each section is a "
        "JSON array of short strings. Sections: %s.\n\nMOM:\n%s"
        % (keys, text[:12000])
    )
    raw = llm_client.chat(system, user, temperature=0.1, max_tokens=2500)
    raw = raw.strip()
    raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()
    data = json.loads(raw)
    out = {}
    for key in SECTIONS:
        values = data.get(key) or []
        if not isinstance(values, list):
            values = [values]
        out[key] = [str(v).strip() for v in values if str(v).strip()][:20]
    _apply_fallbacks(out, text)
    return out


def analyze(text: str) -> dict:
    """Analyse the MOM: LLM first when configured, heuristic fallback."""
    if llm_client.llm_enabled():
        try:
            return _llm_analysis(text)
        except Exception:  # noqa: BLE001 - fall back silently to deterministic mode
            pass
    return heuristic_analysis(text)
