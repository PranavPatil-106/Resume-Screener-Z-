"""
HTTP API for the screening workflow:

    POST /api/screening-sessions/{id}/start            start the background pipeline
    GET  /api/screening-sessions/{id}/progress         poll progress (percent, counts, ETA, steps)
    GET  /api/screening-sessions/{id}/results          ranked candidates + tier counts
    POST /api/screening-sessions/{id}/finish           end session -> temp resume data deleted, results kept
    GET  /api/screening-sessions/{id}/export.csv       export results
    POST /api/screening-sessions/{id}/chat             stateful chat with the results
    POST /api/screening-sessions/{id}/chat/reset
    GET  /api/candidate-results/{id}                   candidate detail
    POST /api/candidate-results/{id}/shortlist
    GET  /api/candidate-results/{id}/summary           downloadable text summary
    POST /api/job-descriptions/parse-text | parse-file build a JD draft from pasted text / uploaded PDF
    GET  /api/dashboard/overview                       dashboard stats + recent sessions

Auth dependencies are injected from main.py (build_router) to avoid circular imports.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

import chat_engine
import screening
from database import RESUME_STORAGE_DIR, get_db
from llm_provider import get_llm_provider, llm_available
from models import (
    CandidateResult,
    JobDescription,
    ScreeningSession,
    SessionRun,
    StagedResume,
    User,
    UserRole,
    get_utc_now,
)
from text_extractor import extract_resume_text
from vector_store import close_session_chroma, remove_session_storage_dir

logger = logging.getLogger(__name__)

MAX_JD_FILE_BYTES = 5 * 1024 * 1024


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ShortlistRequest(BaseModel):
    shortlisted: bool


class ParseJDTextRequest(BaseModel):
    text: str = Field(..., min_length=20, max_length=60000)
    title: Optional[str] = Field(default=None, max_length=255)


# ---------------------------------------------------------------------------
# JD parsing
# ---------------------------------------------------------------------------
_JD_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "category": {"type": "string"},
        "skills": {"type": "array", "items": {"type": "string"}},
        "experience": {"type": "string"},
        "employment_type": {"type": "string"},
    },
    "required": ["title", "category", "skills", "experience", "employment_type"],
}

_CATEGORY_HINTS = [
    ("Engineering", ["engineer", "developer", "software", "backend", "frontend", "devops", "sre", "full stack"]),
    ("Data", ["data scientist", "data analyst", "data engineer", "analytics", "machine learning", "ml "]),
    ("AIML", ["ai engineer", "llm", "generative", "nlp", "deep learning"]),
    ("Design", ["designer", "ux", "ui "]),
    ("Product", ["product manager", "product owner"]),
]


def parse_jd_text(text: str, title_hint: Optional[str] = None) -> dict:
    text = (text or "").strip()[:100000]
    draft: dict[str, Any] = {}
    if llm_available():
        try:
            draft = get_llm_provider().chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "Extract structured fields from a job description. title: the role title. category: one "
                            "word such as Engineering, Data, AIML, Design, Product, Sales, HR, General. skills: up to "
                            "12 key skills/technologies (short names). experience: e.g. '3-5 years' or "
                            "'Not specified'. employment_type: Full-time, Part-time, Contract, or Internship."
                        ),
                    },
                    {"role": "user", "content": text[:8000]},
                ],
                schema=_JD_SCHEMA,
                temperature=0.0,
                max_tokens=1200,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("JD parsing via LLM failed, using heuristic: %s", e)
            draft = {}

    title = (title_hint or str(draft.get("title") or "")).strip()
    if not title:
        first = next((ln.strip(" #*-\t") for ln in text.splitlines() if ln.strip()), "")
        title = first[:80] or "Untitled role"

    skills = [str(s).strip() for s in draft.get("skills", []) if str(s).strip()] if isinstance(draft.get("skills"), list) else []
    if not skills:
        for v in screening.SKILL_VOCAB:
            if screening.text_has_term(text, v):
                skills.append(screening.display_skill(v))
            if len(skills) >= 10:
                break

    experience = str(draft.get("experience") or "").strip()
    if not experience:
        m = re.search(r"(\d{1,2})\s*(?:-|to|–)\s*(\d{1,2})\s*\+?\s*(?:years|yrs)", text, flags=re.I)
        m2 = re.search(r"(\d{1,2})\s*\+\s*(?:years|yrs)|(\d{1,2})\s*(?:years|yrs)", text, flags=re.I)
        if m:
            experience = f"{m.group(1)}-{m.group(2)} years"
        elif m2:
            experience = f"{m2.group(1) or m2.group(2)}+ years"
        else:
            experience = "Not specified"

    category = str(draft.get("category") or "").strip()
    if not category:
        low = f"{title} {text[:1500]}".lower()
        category = next((c for c, keys in _CATEGORY_HINTS if any(k in low for k in keys)), "General")

    return {
        "title": title[:255],
        "category": category[:100] or "General",
        "description": text,
        "skills": skills[:12],
        "experience": experience[:100],
        "employment_type": (str(draft.get("employment_type") or "Full-time").strip() or "Full-time")[:100],
    }


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------
def _iso(dt: Any) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


def _summary(c: CandidateResult, total_requirements: int) -> dict:
    return {
        "id": c.id,
        "resume_id": c.resume_id,
        "name": c.candidate_name or c.original_filename,
        "email": c.email,
        "filename": c.original_filename,
        "experience_years": c.experience_years,
        "match_percent": c.match_percent,
        "tier": c.tier,
        "skills": c.skills or [],
        "shortlisted": bool(c.shortlisted),
        "matched_count": len(c.matched or []),
        "total_requirements": total_requirements,
        "scoring_mode": c.scoring_mode,
    }


def _detail(c: CandidateResult, session: ScreeningSession, run: Optional[SessionRun]) -> dict:
    return {
        **_summary(c, len(run.requirements) if run and run.requirements else len(c.requirement_results or [])),
        "session_id": c.session_id,
        "session_status": session.status,
        "job_title": session.job_description.title if session.job_description else "",
        "requirement_results": c.requirement_results or [],
        "matched": c.matched or [],
        "partial": c.partial or [],
        "missing": c.missing or [],
        "highlights": c.highlights or [],
        "projects": c.projects or [],
        "experience": c.experience or [],
        "assessment": c.assessment,
    }


def _progress_payload(run: Optional[SessionRun], session_id: str) -> dict:
    if run is None:
        return {
            "status": "idle", "stage": None, "percent": 0, "total": 0, "processed": 0, "remaining": 0,
            "eta_seconds": None, "steps": [], "error": None, "scoring_mode": None,
        }
    act = run.activity if isinstance(run.activity, dict) else {}
    st = run.status
    err = run.error
    if st == "running" and not screening.is_running(session_id):
        st, err = "failed", "Processing was interrupted (the server restarted). Click Retry to continue."
    return {
        "status": st,
        "stage": run.stage,
        "percent": run.percent,
        "total": run.total,
        "processed": run.processed,
        "remaining": max((run.total or 0) - (run.processed or 0), 0),
        "eta_seconds": act.get("eta_seconds"),
        "steps": act.get("steps", []),
        "error": err,
        "scoring_mode": run.scoring_mode,
    }


def _csv_safe(value: Any) -> str:
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


# ---------------------------------------------------------------------------
# Candidates directory: expose new-pipeline results in the shape the Candidates page already reads
# ---------------------------------------------------------------------------
def candidate_directory_items(db: Session) -> list[dict]:
    rows = (
        db.query(CandidateResult, JobDescription.title)
        .join(ScreeningSession, ScreeningSession.id == CandidateResult.session_id)
        .join(JobDescription, JobDescription.id == ScreeningSession.job_description_id)
        .filter(CandidateResult.status == "scored")
        .all()
    )
    return [
        {
            "id": c.id,
            "resume_id": c.resume_id,
            "original_filename": c.original_filename,
            "session_id": c.session_id,
            "job_description_title": title,
            "evaluated_at": c.updated_at,
            "overall_score": c.match_percent,
            "max_overall_score": 100.0,
            "evaluation_summary": c.assessment or "",
        }
        for c, title in rows
    ]


def candidate_result_as_evaluation(db: Session, result_id: str) -> Optional[dict]:
    c = db.query(CandidateResult).filter(CandidateResult.id == result_id, CandidateResult.status == "scored").first()
    session = db.get(ScreeningSession, c.session_id) if c else None
    if c is None or session is None:
        return None
    score = {"met": 5.0, "partial": 2.5, "missing": 0.0}
    rubric = []
    for r in c.requirement_results or []:
        ev = r.get("evidence") or ""
        status = r.get("status", "missing")
        rubric.append(
            {
                "criterion": r.get("name", ""),
                "criterion_type": "experience" if r.get("type") == "experience" else "skill",
                "score": score.get(status, 0.0),
                "max_score": 5.0,
                "evidence_status": "not_found_in_resume" if status == "missing" else ("documented" if (ev or r.get("type") == "experience") else "unknown"),
                "explanation": r.get("note") or ("Supported by resume text." if ev else "No mention found in the resume."),
                "evidence_quotes": [ev] if ev else [],
            }
        )
    return {
        "id": c.id,
        "session_id": c.session_id,
        "resume_id": c.resume_id,
        "original_filename": c.original_filename,
        "job_description_id": session.job_description_id,
        "job_title": session.job_description.title if session.job_description else "",
        "overall_score": c.match_percent,
        "max_overall_score": 100.0,
        "rubric": rubric,
        "missing_criteria": list(c.missing or []),
        "unverified_criteria": list(c.partial or []),
        "evaluation_summary": c.assessment or "",
        "model_name": None,
        "evaluated_at": c.updated_at,
    }


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------
def build_router(
    require_admin_or_recruiter: Callable[..., User],
    require_any_authenticated_user: Callable[..., User],
    require_admin_only: Callable[..., User],
) -> APIRouter:
    router = APIRouter()

    def load_session(db: Session, session_id: str, user: User) -> ScreeningSession:
        session = (
            db.query(ScreeningSession)
            .options(joinedload(ScreeningSession.job_description))
            .filter(ScreeningSession.id == session_id)
            .first()
        )
        if session is None or (user.role == UserRole.VIEWER.value and session.status != "completed"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screening session not found.")
        return session

    def ensure_run(db: Session, session_id: str, email: Optional[str] = None) -> SessionRun:
        run = db.get(SessionRun, session_id)
        if run is None:
            run = SessionRun(
                session_id=session_id, created_by_email=email, status="idle", activity={}, requirements=[], chat_state={}
            )
            db.add(run)
            db.commit()
        elif email and not run.created_by_email:
            run.created_by_email = email
            db.commit()
        return run

    # ------------------------------------------------------------------ pipeline
    @router.post("/api/screening-sessions/{session_id}/start")
    def start_screening(
        session_id: str,
        current_user: User = Depends(require_admin_or_recruiter),
        db: Session = Depends(get_db),
    ):
        session = load_session(db, session_id, current_user)
        if session.status != "draft":
            raise HTTPException(status_code=409, detail=f"Session is '{session.status}'; only draft sessions can be screened.")
        count = db.query(StagedResume).filter(StagedResume.screening_session_id == session_id).count()
        if count == 0:
            raise HTTPException(status_code=400, detail="Upload at least one resume before starting.")
        run = ensure_run(db, session_id, current_user.email)
        if not screening.is_running(session_id):
            run.status = "running"
            run.percent = 0
            run.processed = 0
            run.error = None
            db.commit()
            screening.start_pipeline(session_id)
        return _progress_payload(db.get(SessionRun, session_id), session_id)

    @router.get("/api/screening-sessions/{session_id}/progress")
    def get_progress(
        session_id: str,
        current_user: User = Depends(require_any_authenticated_user),
        db: Session = Depends(get_db),
    ):
        load_session(db, session_id, current_user)
        db.expire_all()
        return _progress_payload(db.get(SessionRun, session_id), session_id)

    @router.get("/api/screening-sessions/{session_id}/results")
    def get_results(
        session_id: str,
        current_user: User = Depends(require_any_authenticated_user),
        db: Session = Depends(get_db),
    ):
        session = load_session(db, session_id, current_user)
        run = db.get(SessionRun, session_id)
        rows = (
            db.query(CandidateResult)
            .filter(CandidateResult.session_id == session_id)
            .order_by(CandidateResult.match_percent.desc(), CandidateResult.candidate_name.asc())
            .all()
        )
        scored = [r for r in rows if r.status == "scored"]
        failed = [r for r in rows if r.status == "failed"]
        reqs = list(run.requirements or []) if run else []
        counts = {"all": len(scored), "strong": 0, "good": 0, "partial": 0, "low": 0}
        for r in scored:
            counts[r.tier] = counts.get(r.tier, 0) + 1
        jd = session.job_description
        return {
            "session": {
                "id": session.id,
                "status": session.status,
                "job_description_id": session.job_description_id,
                "job_title": jd.title if jd else "",
                "created_at": _iso(session.created_at),
                "chat_available": session.status == "draft",
            },
            "counts": counts,
            "shortlisted_count": sum(1 for r in scored if r.shortlisted),
            "requirements": reqs,
            "candidates": [_summary(r, len(reqs)) for r in scored],
            "failed": [{"filename": r.original_filename, "error": r.error or "Processing failed."} for r in failed],
            "scoring_mode": run.scoring_mode if run else None,
            "warning": run.error if run and run.status == "completed" else None,
        }

    @router.post("/api/screening-sessions/{session_id}/finish")
    def finish_session(
        session_id: str,
        current_user: User = Depends(require_admin_or_recruiter),
        db: Session = Depends(get_db),
    ):
        """End the session: delete temp resume files, text and vectors; keep structured results."""
        session = load_session(db, session_id, current_user)
        if screening.is_running(session_id):
            raise HTTPException(status_code=409, detail="Screening is still running.")
        for resume in db.query(StagedResume).filter(StagedResume.screening_session_id == session_id).all():
            try:
                p = RESUME_STORAGE_DIR / resume.storage_name
                if p.is_file():
                    p.unlink()
            except OSError:
                pass
            db.delete(resume)
        close_session_chroma(session_id)
        remove_session_storage_dir(RESUME_STORAGE_DIR / session_id)
        has_results = (
            db.query(CandidateResult)
            .filter(CandidateResult.session_id == session_id, CandidateResult.status == "scored")
            .count()
            > 0
        )
        session.status = "completed" if has_results else "ended"
        session.updated_at = get_utc_now()
        run = db.get(SessionRun, session_id)
        if run is not None:
            run.chat_state = {}
        db.commit()
        return {"id": session_id, "status": session.status}

    @router.get("/api/screening-sessions/{session_id}/export.csv")
    def export_csv(
        session_id: str,
        current_user: User = Depends(require_any_authenticated_user),
        db: Session = Depends(get_db),
    ):
        load_session(db, session_id, current_user)
        rows = (
            db.query(CandidateResult)
            .filter(CandidateResult.session_id == session_id, CandidateResult.status == "scored")
            .order_by(CandidateResult.match_percent.desc())
            .all()
        )
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Rank", "Candidate", "Email", "Match %", "Tier", "Experience (yrs)", "Matched", "Partial", "Missing", "Shortlisted", "Assessment"])
        for i, r in enumerate(rows, 1):
            w.writerow(
                [
                    i, _csv_safe(r.candidate_name), _csv_safe(r.email), r.match_percent, r.tier,
                    r.experience_years if r.experience_years is not None else "",
                    _csv_safe("; ".join(r.matched or [])), _csv_safe("; ".join(r.partial or [])),
                    _csv_safe("; ".join(r.missing or [])), "yes" if r.shortlisted else "no", _csv_safe(r.assessment),
                ]
            )
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="screening-results-{session_id[:8]}.csv"'},
        )

    # ------------------------------------------------------------------ candidates
    def load_candidate(db: Session, result_id: str, user: User) -> tuple[CandidateResult, ScreeningSession]:
        c = db.query(CandidateResult).filter(CandidateResult.id == result_id).first()
        if c is None:
            raise HTTPException(status_code=404, detail="Candidate not found.")
        session = load_session(db, c.session_id, user)
        return c, session

    @router.get("/api/candidate-results/{result_id}")
    def candidate_detail(
        result_id: str,
        current_user: User = Depends(require_any_authenticated_user),
        db: Session = Depends(get_db),
    ):
        c, session = load_candidate(db, result_id, current_user)
        return _detail(c, session, db.get(SessionRun, c.session_id))

    @router.post("/api/candidate-results/{result_id}/shortlist")
    def shortlist(
        result_id: str,
        payload: ShortlistRequest,
        current_user: User = Depends(require_admin_or_recruiter),
        db: Session = Depends(get_db),
    ):
        c, _ = load_candidate(db, result_id, current_user)
        c.shortlisted = payload.shortlisted
        db.commit()
        return {"id": c.id, "shortlisted": bool(c.shortlisted)}

    @router.get("/api/candidate-results/{result_id}/summary")
    def candidate_summary(
        result_id: str,
        current_user: User = Depends(require_any_authenticated_user),
        db: Session = Depends(get_db),
    ):
        c, session = load_candidate(db, result_id, current_user)
        jd_title = session.job_description.title if session.job_description else ""
        lines = [
            f"# {c.candidate_name}",
            f"Role screened for: {jd_title}",
            f"Match: {c.match_percent:.0f}% ({c.tier})",
            f"Email: {c.email or 'n/a'}",
            f"Experience: {f'{c.experience_years:g} years' if c.experience_years is not None else 'n/a'}",
            "",
            "## Requirements",
        ]
        icon = {"met": "[met]    ", "partial": "[partial]", "missing": "[missing]"}
        for r in c.requirement_results or []:
            lines.append(f"- {icon.get(r['status'], '')} {r['name']} ({r['type']})")
            if r.get("evidence"):
                lines.append(f"    Evidence: \"{r['evidence']}\"")
        lines += ["", "## Assessment", c.assessment or "", "", "_AI-assisted analysis. A recruiter makes the final decision._"]
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", c.candidate_name or "candidate").strip("_") or "candidate"
        return Response(
            content="\n".join(lines),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{safe}-summary.md"'},
        )

    # ------------------------------------------------------------------ chat
    @router.post("/api/screening-sessions/{session_id}/chat")
    def chat(
        session_id: str,
        payload: ChatRequest,
        current_user: User = Depends(require_admin_or_recruiter),
        db: Session = Depends(get_db),
    ):
        session = load_session(db, session_id, current_user)
        if session.status != "draft":
            raise HTTPException(
                status_code=409,
                detail="Chat is only available while the session is active (resume data is deleted when a session ends).",
            )
        if screening.is_running(session_id):
            raise HTTPException(status_code=409, detail="Screening is still running. Chat opens when results are ready.")
        ensure_run(db, session_id, current_user.email)
        return chat_engine.handle_chat(db, session_id, payload.message)

    @router.post("/api/screening-sessions/{session_id}/chat/reset")
    def chat_reset(
        session_id: str,
        current_user: User = Depends(require_admin_or_recruiter),
        db: Session = Depends(get_db),
    ):
        load_session(db, session_id, current_user)
        chat_engine.reset_chat(db, session_id)
        return {"ok": True}

    # ------------------------------------------------------------------ JD parsing
    @router.post("/api/job-descriptions/parse-text")
    def jd_parse_text(
        payload: ParseJDTextRequest,
        current_user: User = Depends(require_admin_or_recruiter),
    ):
        return parse_jd_text(payload.text, payload.title)

    @router.post("/api/job-descriptions/parse-file")
    async def jd_parse_file(
        file: UploadFile = File(...),
        current_user: User = Depends(require_admin_or_recruiter),
    ):
        ext = Path(file.filename or "").suffix.lower()
        if ext not in (".pdf", ".docx", ".doc", ".txt", ".md"):
            raise HTTPException(status_code=415, detail="Upload a PDF, DOCX, DOC or TXT job description.")
        data = await file.read(MAX_JD_FILE_BYTES + 1)
        if len(data) > MAX_JD_FILE_BYTES:
            raise HTTPException(status_code=413, detail="Job description file is larger than 5 MB.")
        if ext in (".txt", ".md"):
            text = data.decode("utf-8", errors="replace")
        else:
            tmp = RESUME_STORAGE_DIR / f"jd_tmp_{uuid.uuid4().hex}{ext}"
            try:
                tmp.write_bytes(data)
                st, text, err = extract_resume_text(tmp, ext)
            finally:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
            if st != "extracted":
                raise HTTPException(status_code=422, detail=err or "Could not read text from that file.")
        if len((text or "").strip()) < 20:
            raise HTTPException(status_code=422, detail="The file contains too little text to be a job description.")
        return parse_jd_text(text)

    # ------------------------------------------------------------------ JD permanent delete
    @router.delete("/api/job-descriptions/{jd_id}")
    def delete_job_description(
        jd_id: str,
        delete_sessions: bool = False,
        current_user: User = Depends(require_admin_only),
        db: Session = Depends(get_db),
    ):
        """Permanently delete a JD. If screening sessions use it, the caller must pass delete_sessions=true,
        which also deletes those sessions with their resumes, evaluations and candidate results."""
        jd = db.query(JobDescription).filter(JobDescription.id == jd_id).first()
        if jd is None:
            raise HTTPException(status_code=404, detail=f"Job description '{jd_id}' not found.")
        sessions = db.query(ScreeningSession).filter(ScreeningSession.job_description_id == jd_id).all()
        if sessions and not delete_sessions:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": f"'{jd.title}' is used by {len(sessions)} screening session(s).",
                    "session_count": len(sessions),
                },
            )
        sids = [s.id for s in sessions]
        if any(screening.is_running(sid) for sid in sids):
            raise HTTPException(status_code=409, detail="A screening is still running for this job description.")
        stored = (
            [n for (n,) in db.query(StagedResume.storage_name).filter(StagedResume.screening_session_id.in_(sids)).all()]
            if sids
            else []
        )
        if sids:
            db.query(CandidateResult).filter(CandidateResult.session_id.in_(sids)).delete(synchronize_session=False)
            db.query(SessionRun).filter(SessionRun.session_id.in_(sids)).delete(synchronize_session=False)
        db.delete(jd)  # ORM cascade removes its sessions, staged resumes and rubric evaluations
        db.commit()
        # Files only after the DB commit succeeded, so a failed delete never loses files.
        for name in stored:
            try:
                p = RESUME_STORAGE_DIR / name
                if p.is_file():
                    p.unlink()
            except OSError:
                pass
        for sid in sids:
            close_session_chroma(sid)
            remove_session_storage_dir(RESUME_STORAGE_DIR / sid)
        return {"id": jd_id, "deleted_sessions": len(sids)}

    # ------------------------------------------------------------------ dashboard
    @router.get("/api/dashboard/overview")
    def dashboard_overview(
        current_user: User = Depends(require_any_authenticated_user),
        db: Session = Depends(get_db),
    ):
        sess_q = db.query(ScreeningSession)
        if current_user.role == UserRole.VIEWER.value:
            sess_q = sess_q.filter(ScreeningSession.status == "completed")
        sessions = (
            sess_q.options(joinedload(ScreeningSession.job_description))
            .order_by(ScreeningSession.created_at.desc())
            .limit(8)
            .all()
        )
        runs = {r.session_id: r for r in db.query(SessionRun).filter(SessionRun.session_id.in_([s.id for s in sessions])).all()} if sessions else {}
        counts = {
            sid: n
            for sid, n in db.query(CandidateResult.session_id, func.count(CandidateResult.id))
            .filter(CandidateResult.session_id.in_([s.id for s in sessions]))
            .group_by(CandidateResult.session_id)
            .all()
        } if sessions else {}

        recent = []
        for s in sessions:
            run = runs.get(s.id)
            live = run is not None and run.status == "running" and screening.is_running(s.id)
            label = "processing" if live else s.status
            recent.append(
                {
                    "id": s.id,
                    "name": s.job_description.title if s.job_description else "Screening session",
                    "job_title": s.job_description.title if s.job_description else "",
                    "resumes": counts.get(s.id, 0) or (run.total if run else 0),
                    "status": label,
                    "percent": round(run.percent) if live and run else None,
                    "created_by": run.created_by_email if run else None,
                    "created_at": _iso(s.created_at),
                }
            )
        return {
            "stats": {
                "active_sessions": db.query(ScreeningSession).filter(ScreeningSession.status == "draft").count(),
                "job_descriptions": db.query(JobDescription).filter(JobDescription.is_archived.is_(False)).count(),
                "resumes_processed": db.query(CandidateResult).filter(CandidateResult.status == "scored").count(),
                "shortlisted": db.query(CandidateResult).filter(CandidateResult.shortlisted.is_(True)).count(),
            },
            "recent_sessions": recent,
        }

    return router
