"""render_view hydration: build UI blocks from the DB / saved shortlist, never from model-written numbers.

Block envelope (docs/RESPONSE_TEMPLATES.md): {template, title, data, actions}. block_id is added by the handler.
"""
from __future__ import annotations

from app.db.repository import Repository
from app.services import documents as docs
from app.services.jobspec import describe
from app.services.scoring import CRITERIA, band, rank
from app.tools.context import ToolContext, ToolError

TEMPLATES = ("ranked_table", "candidate_cards", "candidate_profile", "comparison_matrix", "score_radar",
             "chart", "jd_card", "document_hits", "kpi_strip")
CRITERION_LABELS = {"skills": "Skills", "experience": "Experience", "relevance": "Role relevance",
                    "education": "Education", "assessments": "Assessments"}


def _ids(a: dict) -> list[int]:
    return [int(i) for i in (a.get("candidate_ids") or [])]


def _shortlist(ctx: ToolContext, ids: list[int], limit: int) -> list[dict]:
    sl = ctx.chat.shortlist or []
    if not sl:
        raise ToolError("No shortlist yet. Call match_candidates first.")
    if ids:
        by_id = {r["candidate_id"]: r for r in sl}
        missing = [i for i in ids if i not in by_id]
        rows = [by_id[i] for i in ids if i in by_id]
        if missing:  # score the extra candidates on the fly against the active spec
            spec = ctx.require_spec()
            extra = ctx.repo.profiles(missing)
            rows += rank(spec, list(extra.values()))
            rows.sort(key=lambda r: -r["score"])
        return rows
    return sl[:limit]


def _scored(ctx: ToolContext, ids: list[int]) -> list[dict]:
    """Score specific candidates against the active spec (fresh, from the DB)."""
    if not ids:
        sl = ctx.chat.shortlist or []
        ids = [r["candidate_id"] for r in sl[:3]]
    if not ids:
        raise ToolError("candidate_ids required (or call match_candidates first)")
    spec = ctx.require_spec()
    profiles = ctx.repo.profiles(ids)
    return rank(spec, [profiles[i] for i in ids if i in profiles])


def _actions(*pairs: tuple[str, str]) -> list[dict]:
    return [{"label": l, "prompt": p} for l, p in pairs]


def build(ctx: ToolContext, a: dict) -> dict:
    t = a.get("template")
    if t not in TEMPLATES:
        raise ToolError(f"unknown template {t!r}; use one of {', '.join(TEMPLATES)}")
    title = (a.get("title") or "").strip()[:140] or t.replace("_", " ").title()
    opts = a.get("options") or {}
    ids = _ids(a)
    limit = max(1, min(int(opts.get("limit") or 10), 50))

    if t == "ranked_table":
        rows = _shortlist(ctx, ids, limit)
        spec = ctx.chat.spec()
        data = {
            "job_title": spec.title if spec else None,
            "criteria": [{"key": c, "label": CRITERION_LABELS[c]} for c in CRITERIA],
            "rows": [{"rank": n + 1, "candidate_id": r["candidate_id"], "full_name": r["full_name"],
                      "last_job_title": r.get("last_job_title"), "total_experience": r.get("total_experience"),
                      "location": r.get("location"), "hire_type": r.get("hire_type"),
                      "score": r["score"], "band": band(r["score"]), "breakdown": r["breakdown"],
                      "matched_skills": r["matched_skills"], "missing_skills": r["missing_skills"],
                      "flags": r.get("flags", [])} for n, r in enumerate(rows)],
        }
        top = [str(r["candidate_id"]) for r in rows[:3]]
        actions = _actions(("Compare top 3", f"Compare candidates {', '.join(top)} side by side"),
                           ("Show as cards", "Show the shortlist as candidate cards"),
                           ("Skill gaps chart", "Show a chart of skill supply in the shortlist"))
        return {"template": t, "title": title, "data": data, "actions": actions}

    if t == "candidate_cards":
        sl = {r["candidate_id"]: r for r in (ctx.chat.shortlist or [])}
        ids = ids or [r["candidate_id"] for r in (ctx.chat.shortlist or [])[:limit]]
        if not ids:
            raise ToolError("candidate_ids required (or call match_candidates first)")
        profiles = ctx.repo.profiles(ids[:12])
        cards = []
        for i in ids[:12]:
            p = profiles.get(i)
            if not p:
                continue
            s = sl.get(i)
            cards.append({"candidate_id": i, "ats_id": p["ats_id"], "full_name": p["full_name"],
                          "last_job_title": p["last_job_title"], "last_company": p["last_company"],
                          "location": p["location"], "hire_type": p["hire_type"],
                          "application_status": p["application_status"],
                          "total_experience": p["total_experience"], "highest_degree": p["highest_degree"],
                          "primary_major": p["primary_major"], "skills": p["skills"], "summary": p["summary"],
                          "score": s["score"] if s else None, "band": band(s["score"]) if s else None,
                          "matched_skills": s["matched_skills"] if s else []})
        return {"template": t, "title": title, "data": {"cards": cards},
                "actions": _actions(("Compare these", "Compare these candidates side by side"))}

    if t == "candidate_profile":
        if not ids:
            raise ToolError("candidate_ids with one id required")
        cid = ids[0]
        p = ctx.repo.profiles([cid]).get(cid)
        if not p:
            raise ToolError(f"candidate {cid} not found")
        scored = None
        if ctx.chat.job_spec:
            scored = rank(ctx.require_spec(), [p])[0]
        data = {**{k: p[k] for k in ("candidate_id", "ats_id", "full_name", "location", "hire_type",
                                     "total_experience", "highest_degree", "primary_major", "gpa",
                                     "last_job_title", "last_company", "application_status", "pipeline_stage",
                                     "status_included", "job_req_id",
                                     "summary", "skills", "experience", "education", "assessments")},
                "score": scored["score"] if scored else None,
                "band": band(scored["score"]) if scored else None,
                "breakdown": scored["breakdown"] if scored else None,
                "matched_skills": scored["matched_skills"] if scored else [],
                "missing_skills": scored["missing_skills"] if scored else [],
                "criteria": [{"key": c, "label": CRITERION_LABELS[c]} for c in CRITERIA]}
        return {"template": t, "title": title, "data": data,
                "actions": _actions(("Interview questions", f"Suggest interview questions for candidate {cid} "
                                                            "based on their gaps"))}

    if t in ("comparison_matrix", "score_radar"):
        results = _scored(ctx, ids[:6])
        if len(results) < 1:
            raise ToolError("no candidates to compare")
        data = {
            "criteria": [{"key": c, "label": CRITERION_LABELS[c]} for c in CRITERIA],
            "candidates": [{"candidate_id": r["candidate_id"], "full_name": r["full_name"], "score": r["score"],
                            "band": band(r["score"]), "breakdown": r["breakdown"],
                            "matched_skills": r["matched_skills"], "missing_skills": r["missing_skills"]}
                           for r in results],
        }
        return {"template": t, "title": title, "data": data, "actions": []}

    if t == "chart":
        metric = a.get("metric") or opts.get("metric")
        if metric == "shortlist_scores":
            rows = _shortlist(ctx, ids, limit)
            series = [{"label": r["full_name"], "value": r["score"]} for r in rows]
            chart_type = opts.get("chart_type") or "bar"
        else:
            if not metric:
                raise ToolError("chart needs metric: " + ", ".join(Repository.METRICS) + " or shortlist_scores")
            scope = ids or None
            if opts.get("scope") == "shortlist" and ctx.chat.shortlist:
                scope = [r["candidate_id"] for r in ctx.chat.shortlist[:limit]]
            try:
                series = ctx.repo.pool_stats(metric, scope)[:20]
            except ValueError as e:
                raise ToolError(str(e)) from None
            series = [{"label": str(r["label"]), "value": r["value"]} for r in series]
            chart_type = opts.get("chart_type") or ("doughnut" if metric.endswith("_mix") else "bar")
        if chart_type not in ("bar", "doughnut", "line", "radar", "pie"):
            chart_type = "bar"
        return {"template": t, "title": title,
                "data": {"metric": metric, "chart_type": chart_type,
                         "labels": [s["label"] for s in series], "values": [s["value"] for s in series]},
                "actions": []}

    if t == "jd_card":
        spec = ctx.require_spec()
        d = describe(spec)
        if spec.doc_id:
            doc = docs.get_document(ctx.settings.docs_path, spec.doc_id, 600)
            d["doc_title"] = doc["title"] if doc else None
        return {"template": t, "title": title, "data": d,
                "actions": _actions(("Find best candidates", "Find the best candidates for this job"))}

    if t == "document_hits":
        doc_ids = a.get("doc_ids") or ([a["doc_id"]] if a.get("doc_id") else [])
        items = docs.list_documents(ctx.settings.docs_path)
        if doc_ids:
            items = [d for d in items if d["doc_id"] in doc_ids]
        return {"template": t, "title": title, "data": {"docs": items[:20]},
                "actions": [{"label": f"Use {d['title'][:30]}", "prompt": f"Use {d['doc_id']} as the job spec "
                             "and find the best candidates"} for d in items[:3] if d["doc_type"] == "jd"]}

    # kpi_strip
    sl = ctx.chat.shortlist or []
    total = ctx.repo.ping()["candidates"]
    kpis = [{"label": "Candidates in pool", "value": total}]
    if sl:
        kpis += [
            {"label": "In shortlist", "value": len(sl)},
            {"label": "Top score", "value": sl[0]["score"]},
            {"label": "Strong or better (70+)", "value": sum(1 for r in sl if r["score"] >= 70)},
            {"label": "Meet all required skills", "value": sum(1 for r in sl if not r["missing_skills"])},
        ]
    return {"template": "kpi_strip", "title": title, "data": {"kpis": kpis}, "actions": []}
