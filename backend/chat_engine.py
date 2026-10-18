"""
Stateful "Chat with Results" engine.

The conversation is NOT replayed to the LLM. Instead a small structured state is kept per session
(SessionRun.chat_state):

    active    resume_ids currently in focus (result of the last search/filter)
    shown     resume_ids already shown to the recruiter (used for "find other candidates")
    filters   human readable list of applied filters
    summary   one-line summary of the conversation so far

Each message is turned into a structured intent (LLM when available, regex heuristic otherwise), executed
against the stored candidate analysis + the session vector collection, and answered with a deterministic,
evidence-backed reply. Only free-form questions need the LLM to compose prose, and only with the few
retrieved chunks as context (minimal LLM context).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from embedding_provider import get_embedding_provider
from llm_provider import get_llm_provider, llm_available
from models import CandidateResult, SessionRun
from screening import (
    SEMANTIC_PARTIAL_DISTANCE,
    SKILL_VOCAB,
    ALIASES,
    find_sentence,
    term_variants,
    text_has_term,
)
from vector_store import get_session_chroma_dir, get_session_collection

logger = logging.getLogger(__name__)

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["search", "compare", "question", "top"]},
        "terms": {"type": "array", "items": {"type": "string"}},
        "exclude_terms": {"type": "array", "items": {"type": "string"}},
        "scope": {"type": "string", "enum": ["all", "previous"]},
        "exclude_previous": {"type": "boolean"},
        "min_years": {"type": "number"},
        "top_n": {"type": "integer"},
    },
    "required": ["action", "terms", "exclude_terms", "scope", "exclude_previous"],
}

_STOP = {
    "these", "those", "them", "the", "same", "a", "an", "any", "that", "this", "experience", "skills", "skill",
    "candidates", "candidate", "people", "profiles", "resumes", "resume", "it", "of", "in", "or", "and", "also",
    "requirement", "requirements", "who", "which", "have", "has", "are", "is", "be", "to", "for", "other",
}
_END = r"(?=$|[,.?;!]|\s+but\b|\s+and\b|\s+who\b|\s+with\b|\s+without\b|\s+that\b|\s+in\b)"

_SCOPE_PREV = re.compile(
    r"\b(which of (these|them|those)|among (these|them|those)|of these|from these|out of these|"
    r"in this list|these candidates|those candidates|narrow (this|it|them) down|filter (these|them))\b",
    re.I,
)
_OTHER = re.compile(r"\b(other|another|more|else|new|different|additional)\b", re.I)
_RESET = re.compile(r"\b(start over|reset|clear (the )?(filters|context|chat))\b", re.I)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
def _fresh_state() -> dict:
    return {"active": [], "shown": [], "filters": [], "summary": "", "last_query": ""}


def get_state(run: Optional[SessionRun]) -> dict:
    st = dict(run.chat_state) if run is not None and isinstance(run.chat_state, dict) else {}
    base = _fresh_state()
    base.update({k: v for k, v in st.items() if k in base})
    return base


def reset_chat(db: Session, session_id: str) -> None:
    run = db.get(SessionRun, session_id)
    if run is not None:
        run.chat_state = _fresh_state()
        db.commit()


# ---------------------------------------------------------------------------
# Intent
# ---------------------------------------------------------------------------
_FILLER = {"the", "same", "a", "an", "any", "some", "these", "those", "requirement", "requirements", "candidates", "candidate"}
_YEARS_RE = re.compile(r"\d+(?:\.\d+)?\s*\+?\s*(?:years?|yrs?)\b", re.I)


def _clean_term(raw: str) -> str:
    t = re.sub(r"\b(experience|skills?|knowledge|background|expertise|exposure)\b", "", raw, flags=re.I)
    t = " ".join(w for w in t.split() if w.lower().strip(",.?;:") not in _FILLER)
    t = re.sub(r"\s+", " ", t).strip(" ,.?;:'\"")
    return t


def _split_terms(raw: str) -> list[str]:
    out = []
    for part in re.split(r",|\band\b|\bor\b|&|/(?!d)", raw):
        if _YEARS_RE.search(part):
            continue  # '5+ years' is a numeric filter, not a skill
        t = _clean_term(part)
        if t and t.lower() not in _STOP and len(t) <= 40 and not re.fullmatch(r"[\d+.\s]+", t):
            out.append(t)
    return out


def _vocab_terms(message: str, extra: list[str]) -> list[str]:
    found = []
    seen: set[str] = set()
    covered: set[str] = set()
    for v in list(extra) + SKILL_VOCAB + list(ALIASES.keys()):
        k = v.lower()
        if k in seen or k in covered or len(k) < 2:
            continue
        if text_has_term(message, v):
            seen.add(k)
            covered |= term_variants(v)
            found.append(v)
    return found


def heuristic_intent(message: str, req_names: list[str]) -> dict:
    low = message.lower()
    exclude: list[str] = []
    for m in re.finditer(r"\bwithout\s+(.+?)" + _END, message, flags=re.I):
        exclude += _split_terms(m.group(1))
    for m in re.finditer(r"\b(?:don'?t|do not|doesn'?t|does not|lack(?:ing|s)?)\s+(?:have\s+|know\s+|mention\s+)?(.+?)" + _END, message, flags=re.I):
        exclude += _split_terms(m.group(1))
    exclude = [e for e in exclude if e]

    terms: list[str] = []
    for m in re.finditer(
        r"\b(?:with|having|has|have|knows?|skilled in|experience (?:in|with)|using|worked (?:on|with))\s+(.+?)" + _END,
        message,
        flags=re.I,
    ):
        terms += _split_terms(m.group(1))
    terms += _vocab_terms(message, req_names)

    ex_low = {e.lower() for e in exclude}
    seen: set[str] = set()
    clean_terms = []
    for t in terms:
        k = t.lower()
        if k in seen or k in ex_low:
            continue
        # drop terms that are only an alias of an excluded term
        if any(k in term_variants(e) for e in exclude):
            continue
        seen.add(k)
        clean_terms.append(t)

    years = None
    ym = re.search(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)", low)
    if ym:
        years = float(ym.group(1))
    topn = None
    tm = re.search(r"\btop\s+(\d{1,2})\b", low)
    if tm:
        topn = int(tm.group(1))

    if re.search(r"\b(compare|versus|\bvs\b|difference between)\b", low):
        action = "compare"
    elif clean_terms or exclude or years is not None:
        action = "search"
    elif re.search(r"\b(top|best|strongest|rank|highest|leading)\b", low):
        action = "top"
    else:
        action = "question"

    return {
        "action": action,
        "terms": clean_terms,
        "exclude_terms": exclude,
        "scope": "previous" if _SCOPE_PREV.search(message) else "all",
        "exclude_previous": bool(_OTHER.search(message)) and not _SCOPE_PREV.search(message),
        "min_years": years,
        "top_n": topn,
    }


def understand(message: str, state: dict, req_names: list[str]) -> dict:
    base = heuristic_intent(message, req_names)
    if not llm_available():
        return base
    try:
        ctx = (
            f"Candidates previously shown: {len(state['shown'])}. Active filters: "
            f"{'; '.join(state['filters']) or 'none'}. Job requirements: {', '.join(req_names[:12]) or 'n/a'}."
        )
        data = get_llm_provider().chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Convert a recruiter's chat message about a pool of screened candidates into a JSON intent.\n"
                        "action: 'search' (find/filter candidates by skills or years), 'compare', 'top' (best/ranked "
                        "candidates, no filter), or 'question' (free-form question about candidates).\n"
                        "terms: skills/technologies the candidates MUST have. exclude_terms: skills they must NOT have "
                        "(from 'without X', \"don't have X\").\n"
                        "scope: 'previous' if the message refers to the candidates just shown ('which of these', "
                        "'among them', 'narrow down'); else 'all'.\n"
                        "exclude_previous: true if asking for OTHER/MORE/NEW candidates than already shown.\n"
                        "min_years: minimum years of experience if stated. top_n: number if stated ('top 3').\n"
                        "Keep skill names short and canonical (e.g. 'AWS', 'RAG', 'LangChain')."
                    ),
                },
                {"role": "user", "content": f"{ctx}\n\nMessage: {message}"},
            ],
            schema=INTENT_SCHEMA,
            temperature=0.0,
            max_tokens=800,
        )
        intent = {
            "action": data.get("action") if data.get("action") in ("search", "compare", "question", "top") else base["action"],
            "terms": [t for t in (str(t).strip() for t in data.get("terms", [])) if t and not _YEARS_RE.search(t)],
            "exclude_terms": [t for t in (str(t).strip() for t in data.get("exclude_terms", [])) if t and not _YEARS_RE.search(t)],
            "scope": data.get("scope") if data.get("scope") in ("all", "previous") else base["scope"],
            "exclude_previous": bool(data.get("exclude_previous", False)),
            "min_years": data.get("min_years") if isinstance(data.get("min_years"), (int, float)) and data.get("min_years") > 0 else base["min_years"],
            "top_n": data.get("top_n") if isinstance(data.get("top_n"), int) and data.get("top_n") > 0 else base["top_n"],
        }
        # A search with nothing to search for is really a question.
        if intent["action"] == "search" and not (intent["terms"] or intent["exclude_terms"] or intent["min_years"]):
            intent["action"] = base["action"]
        return intent
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM intent parsing failed, using heuristic: %s", e)
        return base


# ---------------------------------------------------------------------------
# Evidence lookup
# ---------------------------------------------------------------------------
def _structured_text(c: CandidateResult) -> str:
    parts = list(c.skills or []) + list(c.highlights or []) + list(c.projects or [])
    for r in c.requirement_results or []:
        if r.get("status") in ("met", "partial"):
            parts.append(r.get("name", ""))
            parts.append(r.get("evidence", ""))
    return " \n".join(p for p in parts if p)


def term_hits(
    session_id: str, term: str, pool: list[CandidateResult], allow_semantic: bool
) -> dict[str, str]:
    """resume_id -> evidence snippet for candidates in `pool` that mention `term`."""
    hits: dict[str, str] = {}
    pool_ids = {c.resume_id for c in pool}

    # 1) structured analysis (skills / evidence stored at scoring time)
    for c in pool:
        st = _structured_text(c)
        if st and text_has_term(st, term):
            hits[c.resume_id] = find_sentence(st, term) or term

    # 2) exhaustive lexical scan of the session's chunks + (optional) semantic neighbours
    try:
        if not get_session_chroma_dir(session_id).exists():
            return hits
        col = get_session_collection(session_id)
        total = col.count()
        if total == 0:
            return hits
        got = col.get(include=["documents", "metadatas"], limit=min(total, 20000))
        for doc, meta in zip(got.get("documents", []), got.get("metadatas", [])):
            rid = str((meta or {}).get("resume_id", ""))
            if rid in pool_ids and rid not in hits and text_has_term(doc, term):
                hits[rid] = find_sentence(doc, term) or doc[:200]
        if allow_semantic:
            q = get_embedding_provider().embed_query(f"Experience with {term}")
            res = col.query(
                query_embeddings=[q],
                n_results=min(total, 60),
                include=["documents", "metadatas", "distances"],
            )
            for doc, meta, dist in zip(
                (res.get("documents") or [[]])[0], (res.get("metadatas") or [[]])[0], (res.get("distances") or [[]])[0]
            ):
                rid = str((meta or {}).get("resume_id", ""))
                if rid in pool_ids and rid not in hits and dist <= min(SEMANTIC_PARTIAL_DISTANCE, 0.26):
                    hits[rid] = doc[:200]
    except Exception as e:  # noqa: BLE001
        logger.warning("Chunk lookup failed for term '%s': %s", term, e)
    return hits


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------
def _cand_payload(c: CandidateResult, snippet: str = "") -> dict:
    return {
        "id": c.id,
        "resume_id": c.resume_id,
        "name": c.candidate_name or c.original_filename,
        "match_percent": c.match_percent,
        "tier": c.tier,
        "years": c.experience_years,
        "snippet": (snippet or "")[:220],
    }


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _predicate(terms: list[str], excl: list[str], years: Optional[float]) -> str:
    pos = []
    if terms:
        pos.append(f"{' and '.join(terms)} experience")
    if years:
        pos.append(f"{years:g}+ years of experience")
    pred = " and ".join(pos)
    if excl:
        neg = f"no mention of {' or '.join(excl)}"
        pred = f"{pred} and {neg}" if pred else neg
    return pred


def _suggestions(req_names: list[str], terms: list[str]) -> list[str]:
    skill_reqs = [r for r in req_names if not r.lower().startswith("experience:")]
    out = []
    for r in skill_reqs:
        if r.lower() not in [t.lower() for t in terms]:
            out.append(f"Which of these have {r}?")
        if len(out) >= 2:
            break
    out += ["Compare top 3 candidates", "Find other candidates like these"]
    return out[:4]


def _answer_question(
    session_id: str, message: str, pool: list[CandidateResult], names_in_msg: list[CandidateResult]
) -> tuple[str, list[dict]]:
    focus = names_in_msg or pool
    ids = [c.resume_id for c in focus]
    by_resume = {c.resume_id: c for c in pool}
    chunks: list[tuple[str, str]] = []
    try:
        if get_session_chroma_dir(session_id).exists() and ids:
            col = get_session_collection(session_id)
            total = col.count()
            if total:
                q = get_embedding_provider().embed_query(message)
                kwargs: dict[str, Any] = {}
                if len(ids) < len(by_resume):
                    kwargs["where"] = {"resume_id": {"$in": ids}}
                res = col.query(
                    query_embeddings=[q],
                    n_results=min(total, 6),
                    include=["documents", "metadatas"],
                    **kwargs,
                )
                for doc, meta in zip((res.get("documents") or [[]])[0], (res.get("metadatas") or [[]])[0]):
                    rid = str((meta or {}).get("resume_id", ""))
                    if rid in by_resume:
                        chunks.append((rid, doc))
    except Exception as e:  # noqa: BLE001
        logger.warning("Evidence retrieval for question failed: %s", e)

    cited: dict[str, CandidateResult] = {rid: by_resume[rid] for rid, _ in chunks}
    if not llm_available():
        if not chunks:
            return (
                "I couldn't find relevant evidence in the resumes for that question. "
                "Try naming a skill, e.g. “Which candidates have AWS?”.",
                [],
            )
        lines = [f"- {by_resume[rid].candidate_name}: {doc[:220].strip()}" for rid, doc in chunks[:4]]
        return "Here is the most relevant resume evidence I found:\n" + "\n".join(lines), [
            _cand_payload(c) for c in cited.values()
        ]

    facts = "\n".join(
        f"- {c.candidate_name}: {c.match_percent:.0f}% match, ~{c.experience_years or '?'} yrs, "
        f"matched: {', '.join(c.matched[:6]) or 'none'}; missing: {', '.join(c.missing[:4]) or 'none'}"
        for c in (names_in_msg or pool[:8])
    )
    evidence = "\n\n".join(f"[{by_resume[rid].candidate_name}]\n{doc[:700]}" for rid, doc in chunks) or "(no chunks retrieved)"
    try:
        answer = get_llm_provider().chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You answer recruiter questions about screened candidates. Use ONLY the candidate facts and "
                        "resume evidence provided. Name the candidate for every claim. If the evidence is "
                        "insufficient, say so plainly. Do not infer protected characteristics and do not make "
                        "hire/reject decisions. Be concise (max 6 sentences)."
                    ),
                },
                {"role": "user", "content": f"Candidate facts:\n{facts}\n\nResume evidence:\n{evidence}\n\nQuestion: {message}"},
            ],
            temperature=0.2,
            max_tokens=1500,
        )
        return answer.strip(), [_cand_payload(c) for c in cited.values()]
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM answer failed: %s", e)
        return "I couldn't reach the AI model to answer that. Please try again in a moment.", []


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def handle_chat(db: Session, session_id: str, message: str) -> dict:
    msg = message.strip()
    run = db.get(SessionRun, session_id)
    state = get_state(run)
    results = (
        db.query(CandidateResult)
        .filter(CandidateResult.session_id == session_id, CandidateResult.status == "scored")
        .order_by(CandidateResult.match_percent.desc())
        .all()
    )
    req_names = [r["name"] for r in (run.requirements if run is not None and run.requirements else [])]

    if not results:
        return {
            "answer": "There are no scored candidates in this session yet. Run the screening first.",
            "candidates": [],
            "total": 0,
            "all_ids": [],
            "suggestions": [],
        }

    if _RESET.search(msg):
        reset_chat(db, session_id)
        return {
            "answer": "Done. I cleared the filters, so we're back to all candidates.",
            "candidates": [],
            "total": len(results),
            "all_ids": [],
            "suggestions": _suggestions(req_names, []),
        }

    intent = understand(msg, state, req_names)
    by_resume = {c.resume_id: c for c in results}

    # candidate names mentioned in the message (e.g. "Does Rahul have AWS?")
    low = msg.lower()
    named: list[CandidateResult] = []
    for c in results:
        nm = (c.candidate_name or "").lower().strip()
        if not nm:
            continue
        toks = [t for t in re.split(r"\s+", nm) if len(t) >= 3]
        if nm in low or (toks and (toks[0] in low.split() or (len(toks) > 1 and toks[-1] in low.split()))):
            named.append(c)

    action = intent["action"]
    if named and action in ("search", "top") and not intent["terms"] and not intent["exclude_terms"]:
        action = "question"
    if named and intent["terms"] and action == "search" and len(named) <= 3 and re.search(r"\b(does|do|did|is|has|have)\b", low):
        action = "question"

    top_default = 5
    # ---- compare ---------------------------------------------------------------------------------
    if action == "compare":
        n = int(intent.get("top_n") or (len(named) if len(named) >= 2 else 3))
        if len(named) >= 2:
            subjects = named
        elif intent["scope"] == "previous" and state["active"]:
            subjects = [by_resume[i] for i in state["active"] if i in by_resume] or results
        else:
            subjects = results
        subjects = subjects[: max(2, min(n, 6))]
        lines = []
        for i, c in enumerate(subjects, 1):
            strengths = ", ".join(c.matched[:4]) or "none documented"
            gaps = ", ".join(c.missing[:3]) or "none"
            yrs = f", ~{c.experience_years:g} yrs" if c.experience_years else ""
            lines.append(f"{i}. {c.candidate_name} ({c.match_percent:.0f}% match{yrs}) — strengths: {strengths}; gaps: {gaps}")
        answer = (
            f"Here is a side-by-side comparison of {len(subjects)} {_plural(len(subjects), 'candidate', 'candidates')}:\n"
            + "\n".join(lines)
        )
        state["shown"] = list(dict.fromkeys(state["shown"] + [c.resume_id for c in subjects]))
        _save(db, run, state, msg)
        return {
            "answer": answer,
            "candidates": [_cand_payload(c) for c in subjects],
            "total": len(subjects),
            "all_ids": [c.resume_id for c in subjects],
            "suggestions": _suggestions(req_names, []),
        }

    # ---- free-form question ---------------------------------------------------------------------
    if action == "question":
        pool = [by_resume[i] for i in state["active"] if i in by_resume] if intent["scope"] == "previous" and state["active"] else results
        answer, cands = _answer_question(session_id, msg, pool, named)
        _save(db, run, state, msg)
        return {
            "answer": answer,
            "candidates": cands,
            "total": len(cands),
            "all_ids": [c["resume_id"] for c in cands],
            "suggestions": _suggestions(req_names, []),
        }

    # ---- top ranked ------------------------------------------------------------------------------
    if action == "top" and not (intent["terms"] or intent["exclude_terms"] or intent["min_years"]):
        n = int(intent.get("top_n") or top_default)
        pool = [by_resume[i] for i in state["active"] if i in by_resume] if intent["scope"] == "previous" and state["active"] else results
        top = pool[:n]
        lines = [f"{i}. {c.candidate_name} ({c.match_percent:.0f}% match)" for i, c in enumerate(top, 1)]
        answer = f"Here are the top {len(top)} candidates by match score:\n" + "\n".join(lines)
        state["shown"] = list(dict.fromkeys(state["shown"] + [c.resume_id for c in top]))
        _save(db, run, state, msg)
        return {
            "answer": answer,
            "candidates": [_cand_payload(c) for c in top],
            "total": len(pool),
            "all_ids": [c.resume_id for c in pool][:500],
            "suggestions": _suggestions(req_names, []),
        }

    # ---- search / filter ---------------------------------------------------------------------------
    use_prev = intent["scope"] == "previous" and bool(state["active"])
    pool = [by_resume[i] for i in state["active"] if i in by_resume] if use_prev else list(results)
    if intent["exclude_previous"]:
        pool = [c for c in pool if c.resume_id not in set(state["shown"])]
    if intent["min_years"]:
        pool = [c for c in pool if (c.experience_years or 0) >= float(intent["min_years"])]

    snippets: dict[str, str] = {}
    for term in intent["terms"]:
        hits = term_hits(session_id, term, pool, allow_semantic=True)
        pool = [c for c in pool if c.resume_id in hits]
        for rid, s in hits.items():
            snippets.setdefault(rid, s)
    for term in intent["exclude_terms"]:
        hits = term_hits(session_id, term, pool, allow_semantic=False)
        pool = [c for c in pool if c.resume_id not in hits]

    n = len(pool)
    pred = _predicate(intent["terms"], intent["exclude_terms"], intent.get("min_years"))
    if intent["exclude_previous"]:
        pred = (pred + " " if pred else "") + "(not shown before)"
    cands_all = pool  # already sorted by match desc
    k = int(intent.get("top_n") or top_default)
    top = cands_all[:k]

    if n == 0:
        answer = (
            f"I couldn't find any candidates with {pred or 'those criteria'}"
            + (" among the previous results." if use_prev else ".")
            + " Try loosening a filter or asking about a related skill."
        )
    else:
        if use_prev:
            head = f"Among these, {n} {_plural(n, 'candidate has', 'candidates have')} {pred}."
        else:
            head = f"I found {n} {_plural(n, 'candidate', 'candidates')} with {pred}."
        lines = [f"{i}. {c.candidate_name} ({c.match_percent:.0f}% match)" for i, c in enumerate(top, 1)]
        answer = f"{head} Here {_plural(len(top), 'is the top candidate', f'are the top {len(top)}')}:\n" + "\n".join(lines)

    # update structured state (no conversation replay needed)
    if n > 0:
        state["active"] = [c.resume_id for c in cands_all][:1000]
        state["shown"] = list(dict.fromkeys(state["shown"] + [c.resume_id for c in top]))
    flt = _predicate(intent["terms"], intent["exclude_terms"], intent.get("min_years"))
    if flt:
        state["filters"] = (state["filters"] if use_prev else []) + [flt]
    state["summary"] = f"{n} candidates after: {'; '.join(state['filters'])}"[:500]
    _save(db, run, state, msg)

    return {
        "answer": answer,
        "candidates": [_cand_payload(c, snippets.get(c.resume_id, "")) for c in top],
        "total": n,
        "all_ids": [c.resume_id for c in cands_all][:500],
        "suggestions": _suggestions(req_names, intent["terms"]),
    }


def _save(db: Session, run: Optional[SessionRun], state: dict, msg: str) -> None:
    if run is None:
        return
    state["last_query"] = msg[:300]
    run.chat_state = dict(state)
    db.commit()
