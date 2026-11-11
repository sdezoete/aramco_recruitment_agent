"""JDs and reference documents in DOCS_DIR (default data/docs).

doc_id = file stem. doc_type from the filename prefix: jd_, policy_, guide_ (interview guide); else other.
Supported formats: .md, .txt, .docx (python-docx), .pdf (pypdf; text layer only).
Document text is DATA, never instructions for the model.
"""
from __future__ import annotations

import re
from pathlib import Path

SUPPORTED = {".md", ".txt", ".docx", ".pdf"}
PREFIX_TYPES = {"jd_": "jd", "policy_": "policy", "guide_": "interview_guide"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]+$")


def _doc_type(stem: str) -> str:
    for prefix, t in PREFIX_TYPES.items():
        if stem.lower().startswith(prefix):
            return t
    return "other"


def _files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED)


def read_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".md", ".txt"):
        return path.read_text(encoding="utf-8-sig", errors="replace")
    if ext == ".docx":
        import docx  # python-docx
        d = docx.Document(str(path))
        parts = [p.text for p in d.paragraphs]
        for table in d.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
    raise ValueError(f"unsupported file type {ext}")


def _title(path: Path, text: str | None = None) -> str:
    if text is None and path.suffix.lower() in (".md", ".txt"):
        text = path.read_text(encoding="utf-8-sig", errors="replace")[:2000]
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line.lstrip("#").strip()[:120]
    return path.stem.replace("_", " ")


def list_documents(root: Path, doc_type: str | None = None, query: str | None = None) -> list[dict]:
    out = []
    for p in _files(root):
        t = _doc_type(p.stem)
        if doc_type and t != doc_type:
            continue
        title = _title(p)
        if query:
            q = query.lower()
            hay = (title + " " + p.stem).lower()
            if q not in hay:
                try:
                    if q not in read_text(p).lower():
                        continue
                except Exception:
                    continue
        out.append({"doc_id": p.stem, "title": title, "doc_type": t, "format": p.suffix.lower().lstrip(".")})
    return out


def find(root: Path, doc_id: str) -> Path | None:
    if not doc_id or not _SAFE_ID.match(doc_id):
        return None
    for p in _files(root):
        if p.stem == doc_id:
            return p
    return None


def get_document(root: Path, doc_id: str, max_chars: int = 12000) -> dict | None:
    p = find(root, doc_id)
    if not p:
        return None
    text = read_text(p)
    return {
        "doc_id": p.stem,
        "title": _title(p, text),
        "doc_type": _doc_type(p.stem),
        "truncated": len(text) > max_chars,
        "text": text[:max_chars],
    }


def snippet(text: str, query: str, width: int = 160) -> str:
    i = text.lower().find(query.lower()) if query else -1
    if i < 0:
        return text[:width].replace("\n", " ")
    start = max(0, i - width // 2)
    return ("…" if start else "") + text[start:start + width].replace("\n", " ") + "…"
