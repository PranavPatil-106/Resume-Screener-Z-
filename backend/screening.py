"""
Screening engine: one background pipeline per screening session.

    extract text -> embed chunks -> store in vector DB -> evaluate every candidate -> prepare results

* ZIP archives are split so every file inside becomes its own candidate.
* The Job Description is turned into required / preferred requirements once per session.
* Each candidate is analysed by the configured LLM (see llm_provider.py) against ALL requirements in a
  single call, using the resume text / retrieved chunks. The result is verified (quotes must exist in the
  resume), scored deterministically, and stored in `candidate_results`.
* If the LLM is unavailable (or keeps failing) the engine falls back to a transparent keyword + semantic
  heuristic so a screening run never dead-ends. The mode used is stored per candidate.
* Only structured analysis is persisted. Resume files, extracted text and vectors stay temporary.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from chunker import TextChunker
from database import RESUME_STORAGE_DIR, SessionLocal
from embedding_provider import get_embedding_provider
from llm_provider import get_llm_provider, llm_available
from models import CandidateResult, ScreeningSession, SessionRun, StagedResume, get_utc_now
from text_extractor import extract_resume_text, extract_zip_members
from vector_store import cleanup_old_collections, get_session_collection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
SCREENING_CONCURRENCY = max(1, int(os.getenv("SCREENING_CONCURRENCY", "3")))
SEMANTIC_PARTIAL_DISTANCE = float(os.getenv("SEMANTIC_PARTIAL_DISTANCE", "0.33"))
MAX_FULL_TEXT_CHARS = 7000
MAX_REQUIREMENTS = 14

TIER_STRONG = 80.0
TIER_GOOD = 65.0
TIER_PARTIAL = 45.0

STEP_DEFS = [
    ("extract", "Extracting text from resumes"),
    ("embed", "Generating embeddings"),
    ("store", "Storing in vector database"),
    ("evaluate", "Evaluating candidates against the job description"),
    ("prepare", "Preparing screening results"),
]

SKILL_VOCAB = [
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "golang", "rust", "ruby", "php", "scala", "kotlin",
    "swift", "sql", "nosql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "kafka", "spark", "hadoop",
    "airflow", "dbt", "snowflake", "bigquery", "react", "angular", "vue", "node.js", "django", "flask", "fastapi",
    "spring", "html", "css", "docker", "kubernetes", "terraform", "ansible", "jenkins", "ci/cd", "git", "linux",
    "aws", "azure", "gcp", "machine learning", "deep learning", "nlp", "computer vision", "llm", "rag",
    "langchain", "langgraph", "llamaindex", "openai", "hugging face", "pytorch", "tensorflow", "scikit-learn",
    "pandas", "numpy", "vector database", "chromadb", "pinecone", "faiss", "prompt engineering", "mlops",
    "rest api", "graphql", "microservices", "agile", "scrum", "tableau", "power bi", "excel", "data analysis",
    "statistics", "leadership", "team management",
]

ALIASES: dict[str, list[str]] = {
    "rag": ["rag", "retrieval augmented generation", "retrieval-augmented generation", "retrieval augmented"],
    "llm": ["llm", "llms", "large language model", "large language models"],
    "aws": ["aws", "amazon web services", "ec2", "sagemaker", "bedrock"],
    "gcp": ["gcp", "google cloud", "vertex ai", "bigquery"],
    "azure": ["azure"],
    "kubernetes": ["kubernetes", "k8s"],
    "javascript": ["javascript", "js", "node.js", "nodejs"],
    "typescript": ["typescript", "ts"],
    "machine learning": ["machine learning", "ml"],
    "nlp": ["nlp", "natural language processing"],
    "docker": ["docker", "containerization", "containerisation"],
    "ci/cd": ["ci/cd", "cicd", "continuous integration", "jenkins", "github actions"],
    "postgresql": ["postgresql", "postgres"],
    "react": ["react", "react.js", "reactjs"],
    "vector database": ["vector database", "vector db", "vector store", "chromadb", "pinecone", "faiss", "weaviate"],
    "golang": ["golang", "go"],
}


DIRECTIONAL_ALIAS_KEYS = {"aws", "gcp"}

DISPLAY_NAMES = {
    "langchain": "LangChain", "langgraph": "LangGraph", "llamaindex": "LlamaIndex", "openai": "OpenAI",
    "pytorch": "PyTorch", "tensorflow": "TensorFlow", "postgresql": "PostgreSQL", "mysql": "MySQL",
    "mongodb": "MongoDB", "fastapi": "FastAPI", "nlp": "NLP", "llm": "LLM", "rag": "RAG", "aws": "AWS",
    "gcp": "GCP", "ci/cd": "CI/CD", "node.js": "Node.js", "javascript": "JavaScript", "typescript": "TypeScript",
    "bigquery": "BigQuery", "chromadb": "ChromaDB", "scikit-learn": "scikit-learn", "hugging face": "Hugging Face",
    "power bi": "Power BI", "mlops": "MLOps", "graphql": "GraphQL", "sql": "SQL", "nosql": "NoSQL",
    "html": "HTML", "css": "CSS", "faiss": "FAISS", "rest api": "REST API", "dbt": "dbt", "c++": "C++",
    "c#": "C#", "php": "PHP", "aws lambda": "AWS Lambda",
}


def display_skill(v: str) -> str:
    return DISPLAY_NAMES.get(v.lower(), v.title() if v.islower() else v)


def term_variants(term: str) -> set[str]:
    """Synonym set for a skill. Cloud-provider groups only expand FROM the provider name
    (aws -> ec2/lambda...), never backwards (lambda != aws), to avoid false matches."""
    t = (term or "").lower().strip()
    out = {t} if t else set()
    for key, vs in ALIASES.items():
        if t == key:
            out |= set(vs)
        elif t in vs and key not in DIRECTIONAL_ALIAS_KEYS:
            out |= set(vs)
            out.add(key)
    return out


def text_has_term(text: str, term: str) -> bool:
    low = (text or "").lower()
    for v in term_variants(term):
        if not v:
            continue
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(v) + r"(?![A-Za-z0-9])", low):
            return True
    return False


def find_sentence(text: str, term: str, max_len: int = 240) -> str:
    """First line / sentence of `text` that mentions `term` (or an alias)."""
    for raw in re.split(r"[\n\r]+", text or ""):
        line = raw.strip(" \t•-*▪●")
        if len(line) < 3:
            continue
        if text_has_term(line, term):
            return line[:max_len].strip()
    return ""


def verify_quote(quote: str, source: str) -> bool:
    if not isinstance(quote, str):
        return False
    q = quote.strip().strip('"“”')
    if len(q) < 4:
        return False
    if q in source or q.lower() in source.lower():
        return True

    def norm(t: str) -> str:
        return " ".join(re.sub(r"[•▪●\-*]", " ", t).split()).lower()

    return norm(q) in norm(source)


def tier_for(percent: float) -> str:
    if percent >= TIER_STRONG:
        return "strong"
    if percent >= TIER_GOOD:
        return "good"
    if percent >= TIER_PARTIAL:
        return "partial"
    return "low"


# ---------------------------------------------------------------------------
# Requirements (Job Description -> list of criteria)
# ---------------------------------------------------------------------------
REQ_SCHEMA = {
    "type": "object",
    "properties": {
        "required": {"type": "array", "items": {"type": "string"}},
        "preferred": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["required", "preferred"],
}


def _parse_min_years(text: str) -> Optional[float]:
    m = re.search(r"(\d+(?:\.\d+)?)", text or "")
    return float(m.group(1)) if m else None


def build_requirements(jd: Any) -> list[dict]:
    """Return [{name, type: required|preferred|experience, query}] for a JobDescription row."""
    skills = [str(s).strip() for s in (jd.skills or []) if str(s).strip()] if isinstance(jd.skills, list) else []
    required: list[str] = []
    preferred: list[str] = []

    if llm_available() and (jd.description or "").strip():
        try:
            data = get_llm_provider().chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "You extract hiring requirements from job descriptions. Return short skill / "
                            "qualification names (max 5 words each), no sentences. 'required' = must-have, "
                            "'preferred' = nice-to-have / plus / bonus. Max 8 required, 5 preferred. "
                            "Do not include years of experience (handled separately)."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Job title: {jd.title}\nListed skills: {', '.join(skills) or 'none'}\n"
                            f"Description:\n{(jd.description or '')[:6000]}\n\n"
                            'Return JSON: {"required": [...], "preferred": [...]}'
                        ),
                    },
                ],
                schema=REQ_SCHEMA,
                temperature=0.0,
                max_tokens=1500,
            )
            required = [str(x).strip() for x in data.get("required", []) if str(x).strip()]
            preferred = [str(x).strip() for x in data.get("preferred", []) if str(x).strip()]
        except Exception as e:  # noqa: BLE001
            logger.warning("Requirement extraction via LLM failed: %s", e)

    # Listed skills are always required.
    seen: set[str] = set()
    ordered: list[tuple[str, str]] = []
    for name in skills + required:
        k = name.lower()
        if k not in seen:
            seen.add(k)
            ordered.append((name, "required"))
    for name in preferred:
        k = name.lower()
        if k not in seen:
            seen.add(k)
            ordered.append((name, "preferred"))

    if not ordered:  # fall back to vocabulary scan of the description
        desc = jd.description or ""
        for v in SKILL_VOCAB:
            if text_has_term(desc, v) and v not in seen:
                seen.add(v)
                ordered.append((v, "required"))
        if not ordered:
            ordered.append((jd.title, "required"))

    reqs = [
        {"name": n, "type": t, "query": f"Experience with {n}"} for n, t in ordered[: MAX_REQUIREMENTS - 1]
    ]
    exp = (jd.experience or "").strip()
    if exp and exp.lower() not in ("not specified", "none", "n/a"):
        reqs.append(
            {
                "name": f"Experience: {exp}",
                "type": "experience",
                "query": f"Work experience and years of professional experience, {exp}",
            }
        )
    return reqs


# ---------------------------------------------------------------------------
# Resume understanding helpers (heuristic)
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_HEADER_WORDS = {
    "resume", "curriculum", "vitae", "cv", "profile", "summary", "objective", "contact", "experience", "education",
    "skills", "projects", "address", "phone", "email", "mobile", "linkedin", "github",
}


def guess_name(text: str, filename: str) -> str:
    for raw in (text or "").splitlines()[:12]:
        line = raw.strip(" \t|•-*")
        if not line or len(line) > 40 or any(ch.isdigit() for ch in line) or "@" in line:
            continue
        words = line.split()
        if not 1 < len(words) <= 4:
            continue
        if any(w.lower().strip(",.:") in _HEADER_WORDS for w in words):
            continue
        if all(re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", w) for w in words):
            return " ".join(w.capitalize() if w.isupper() or w.islower() else w for w in words)
    stem = Path(filename).stem
    stem = re.sub(r"[_\-.]+", " ", stem)
    stem = re.sub(r"\b(resume|cv|curriculum|vitae|final|updated|new)\b", "", stem, flags=re.I)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem.title() if stem else filename


def guess_years(text: str) -> Optional[float]:
    vals = []
    for m in re.finditer(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)", text or "", flags=re.I):
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        if 0 < v <= 45:
            vals.append(v)
    return max(vals) if vals else None


def guess_skills(text: str, requirements: list[dict], limit: int = 12) -> list[str]:
    found: list[str] = []
    for r in requirements:
        if r["type"] != "experience" and text_has_term(text, r["name"]):
            found.append(r["name"])
    for v in SKILL_VOCAB:
        if len(found) >= limit:
            break
        if v not in [f.lower() for f in found] and text_has_term(text, v):
            found.append(display_skill(v))
    return found[:limit]


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
_chroma_lock = threading.Lock()


def retrieve_for_resume(col: Any, resume_id: str, query_embeddings: list[list[float]], top_k: int = 2) -> list[list[dict]]:
    if not query_embeddings:
        return []
    try:
        with _chroma_lock:
            ids = col.get(where={"resume_id": resume_id}, include=[]).get("ids", [])
            n = len(ids)
            if n == 0:
                return [[] for _ in query_embeddings]
            res = col.query(
                query_embeddings=query_embeddings,
                n_results=min(top_k, n),
                where={"resume_id": resume_id},
                include=["documents", "metadatas", "distances"],
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("Vector retrieval failed for %s: %s", resume_id, e)
        return [[] for _ in query_embeddings]
    out: list[list[dict]] = []
    for qi in range(len(query_embeddings)):
        docs = (res.get("documents") or [[]])[qi] if qi < len(res.get("documents") or []) else []
        metas = (res.get("metadatas") or [[]])[qi] if qi < len(res.get("metadatas") or []) else []
        dists = (res.get("distances") or [[]])[qi] if qi < len(res.get("distances") or []) else []
        out.append(
            [
                {
                    "text": docs[i],
                    "index": int((metas[i] or {}).get("chunk_index", i)),
                    "distance": float(dists[i]) if i < len(dists) else 1.0,
                }
                for i in range(len(docs))
            ]
        )
    return out


def store_chunks(
    session_id: str, resume_id: str, filename: str, chunks: list[dict], embeddings: list[list[float]], model_name: str
) -> int:
    if not chunks:
        return 0
    with _chroma_lock:
        col = get_session_collection(session_id, model_name=model_name)
        try:
            col.delete(where={"resume_id": resume_id})
        except Exception:  # noqa: BLE001
            pass
        col.add(
            ids=[f"{resume_id}_{c['index']}" for c in chunks],
            documents=[c["text"] for c in chunks],
            embeddings=embeddings,
            metadatas=[
                {
                    "session_id": session_id,
                    "resume_id": resume_id,
                    "source_filename": filename,
                    "chunk_index": c["index"],
                    "model_name": model_name,
                }
                for c in chunks
            ],
        )
    return len(chunks)


def build_context(text: str, retrieved: list[list[dict]]) -> str:
    """Full resume when small; otherwise header + the most relevant retrieved chunks (RAG)."""
    if len(text) <= MAX_FULL_TEXT_CHARS:
        return text
    uniq: dict[int, str] = {}
    for per_req in retrieved:
        for c in per_req:
            uniq.setdefault(c["index"], c["text"])
    parts, used = [], 0
    for idx in sorted(uniq):
        if used + len(uniq[idx]) > 5500:
            break
        parts.append(uniq[idx])
        used += len(uniq[idx])
    return text[:1200] + "\n...\n" + "\n---\n".join(parts)


# ---------------------------------------------------------------------------
# Candidate analysis
# ---------------------------------------------------------------------------
ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "candidate_name": {"type": "string"},
        "email": {"type": "string"},
        "experience_years": {"type": "number"},
        "skills": {"type": "array", "items": {"type": "string"}},
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "status": {"type": "string", "enum": ["met", "partial", "missing"]},
                    "evidence": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["index", "status", "evidence", "note"],
            },
        },
        "highlights": {"type": "array", "items": {"type": "string"}},
        "projects": {"type": "array", "items": {"type": "string"}},
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "company": {"type": "string"},
                    "period": {"type": "string"},
                },
                "required": ["title", "company", "period"],
            },
        },
        "assessment": {"type": "string"},
    },
    "required": ["candidate_name", "experience_years", "skills", "requirements", "highlights", "assessment"],
}

ANALYSIS_SYSTEM = (
    "You are a precise, fair recruiting analyst. Evaluate ONE candidate resume against a job's requirements.\n"
    "Rules:\n"
    "1. Use ONLY the resume text provided. Never invent facts.\n"
    "2. For every requirement give a status: 'met' = clearly demonstrated in the resume; 'partial' = related, "
    "adjacent or weakly evidenced; 'missing' = no evidence in the text.\n"
    "3. 'evidence' MUST be a verbatim quote (max 30 words) copied exactly from the resume, or an empty string.\n"
    "4. 'note' is one short factual sentence.\n"
    "5. candidate_name is the person's name from the resume header. experience_years is total professional "
    "experience in years (number, estimate from dates if needed, 0 if unknown).\n"
    "6. skills = up to 10 of the candidate's most relevant skills. highlights = up to 4 concise achievements. "
    "projects = up to 3 project names with a few words each. experience = up to 4 most recent roles.\n"
    "7. assessment = 2 sentences summarising fit based on evidence. Do NOT recommend hire/reject.\n"
    "8. Ignore protected characteristics (age, gender, religion, nationality, marital status, etc.)."
)


def _normalize_status(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v in ("met", "yes", "full", "matched", "strong"):
        return "met"
    if v in ("partial", "partially", "some", "weak", "related"):
        return "partial"
    return "missing"


class LLMGate:
    """Circuit breaker: stop calling the LLM for the rest of a run if it keeps failing."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.failures = 0
        self.successes = 0

    def allowed(self) -> bool:
        with self.lock:
            return llm_available() and not (self.failures >= 3 and self.successes == 0)

    def record(self, ok: bool) -> None:
        with self.lock:
            if ok:
                self.successes += 1
            else:
                self.failures += 1


def llm_analyze(text: str, jd_title: str, requirements: list[dict], retrieved: list[list[dict]]) -> dict:
    req_lines = "\n".join(f"[{i}] {r['name']} ({r['type']})" for i, r in enumerate(requirements))
    user = (
        f"JOB TITLE: {jd_title}\n\nREQUIREMENTS:\n{req_lines}\n\n"
        f"RESUME TEXT:\n\"\"\"\n{build_context(text, retrieved)}\n\"\"\"\n\n"
        "Return JSON with: candidate_name, email, experience_years, skills[], "
        "requirements[{index,status,evidence,note}] (one entry per requirement index), highlights[], projects[], "
        "experience[{title,company,period}], assessment."
    )
    return get_llm_provider().chat_json(
        [{"role": "system", "content": ANALYSIS_SYSTEM}, {"role": "user", "content": user}],
        schema=ANALYSIS_SCHEMA,
        temperature=0.0,
        max_tokens=4096,
    )


def heuristic_analyze(text: str, requirements: list[dict], retrieved: list[list[dict]]) -> dict:
    reqs_out = []
    for i, r in enumerate(requirements):
        chunks = retrieved[i] if i < len(retrieved) else []
        best_dist = min((c["distance"] for c in chunks), default=1.0)
        if r["type"] == "experience":
            reqs_out.append({"index": i, "status": "missing", "evidence": "", "note": ""})
            continue
        if text_has_term(text, r["name"]):
            ev = find_sentence(text, r["name"])
            reqs_out.append({"index": i, "status": "met", "evidence": ev, "note": "Mentioned in the resume."})
        elif chunks and best_dist <= SEMANTIC_PARTIAL_DISTANCE:
            reqs_out.append(
                {
                    "index": i,
                    "status": "partial",
                    "evidence": "",
                    "note": "Related content found by semantic search; not stated explicitly.",
                }
            )
        else:
            reqs_out.append({"index": i, "status": "missing", "evidence": "", "note": "No mention found."})
    return {"requirements": reqs_out}


def finalize_analysis(
    parsed: dict, text: str, filename: str, requirements: list[dict], mode: str
) -> dict:
    """Validate/normalise model or heuristic output and compute the deterministic score."""
    by_index: dict[int, dict] = {}
    for item in parsed.get("requirements", []) if isinstance(parsed.get("requirements"), list) else []:
        if isinstance(item, dict):
            try:
                by_index[int(item.get("index"))] = item
            except (TypeError, ValueError):
                continue

    name = str(parsed.get("candidate_name") or "").strip()
    if not name or name.lower() in ("unknown", "n/a", "none", "not found", "candidate"):
        name = guess_name(text, filename)
    email = str(parsed.get("email") or "").strip()
    if not EMAIL_RE.fullmatch(email):
        m = EMAIL_RE.search(text)
        email = m.group(0) if m else ""
    years: Optional[float]
    try:
        years = float(parsed.get("experience_years")) if parsed.get("experience_years") is not None else None
    except (TypeError, ValueError):
        years = None
    if years is None or years <= 0:
        years = guess_years(text)
    if years is not None:
        years = round(min(max(years, 0.0), 45.0), 1)

    req_results: list[dict] = []
    for i, r in enumerate(requirements):
        item = by_index.get(i, {})
        status = _normalize_status(item.get("status"))
        evidence = str(item.get("evidence") or "").strip()
        note = str(item.get("note") or "").strip()

        if r["type"] == "experience":
            min_years = _parse_min_years(r["name"])
            if years is not None and min_years:
                if years >= min_years:
                    status = "met"
                elif years >= 0.7 * min_years:
                    status = "partial"
                else:
                    status = "missing"
                note = f"Approx. {years:g} years of experience vs {min_years:g} required."
            elif years is None and status != "missing":
                status = "partial"
        else:
            fabricated = False
            if evidence and not verify_quote(evidence, text):
                fabricated = True  # the model cited text that is not in the resume
                evidence = find_sentence(text, r["name"])
            if not evidence and status in ("met", "partial"):
                evidence = find_sentence(text, r["name"])
            if fabricated and not evidence:
                status = "missing"
                note = "Claimed evidence could not be verified in the resume."
            elif status == "met" and not evidence:
                status = "partial"
            if status == "missing" and text_has_term(text, r["name"]):
                # model said missing but the literal skill is in the resume: trust the text
                status = "met"
                evidence = find_sentence(text, r["name"])
                note = note or "Mentioned in the resume."

        req_results.append(
            {"name": r["name"], "type": r["type"], "status": status, "evidence": evidence[:300], "note": note[:300]}
        )

    weights = {"required": 1.0, "experience": 1.0, "preferred": 0.5}
    value = {"met": 1.0, "partial": 0.5, "missing": 0.0}
    total_w = sum(weights.get(x["type"], 1.0) for x in req_results) or 1.0
    got = sum(weights.get(x["type"], 1.0) * value[x["status"]] for x in req_results)
    percent = round(100.0 * got / total_w, 1)

    matched = [x["name"] for x in req_results if x["status"] == "met"]
    partial = [x["name"] for x in req_results if x["status"] == "partial"]
    missing = [x["name"] for x in req_results if x["status"] == "missing"]

    skills = [str(s).strip() for s in parsed.get("skills", []) if str(s).strip()] if isinstance(parsed.get("skills"), list) else []
    if not skills:
        skills = guess_skills(text, requirements)
    skills = skills[:12]

    def _strs(key: str, limit: int) -> list[str]:
        v = parsed.get(key)
        return [str(s).strip()[:300] for s in v if str(s).strip()][:limit] if isinstance(v, list) else []

    experience: list[dict] = []
    if isinstance(parsed.get("experience"), list):
        for e in parsed["experience"][:4]:
            if isinstance(e, dict):
                experience.append(
                    {
                        "title": str(e.get("title") or "")[:120],
                        "company": str(e.get("company") or "")[:120],
                        "period": str(e.get("period") or "")[:60],
                    }
                )

    assessment = str(parsed.get("assessment") or "").strip()
    if not assessment:
        total = len(req_results)
        assessment = f"Meets {len(matched)} of {total} requirements"
        if partial:
            assessment += f" and partially meets {len(partial)}"
        assessment += "."
        if missing:
            assessment += f" No evidence found for: {', '.join(missing[:4])}."

    return {
        "candidate_name": name[:255],
        "email": email[:255] or None,
        "experience_years": years,
        "skills": skills,
        "requirement_results": req_results,
        "matched": matched,
        "partial": partial,
        "missing": missing,
        "highlights": _strs("highlights", 4),
        "projects": _strs("projects", 3),
        "experience": experience,
        "assessment": assessment[:1500],
        "match_percent": percent,
        "tier": tier_for(percent),
        "scoring_mode": mode,
    }


def analyze_candidate(
    text: str, filename: str, jd_title: str, requirements: list[dict], retrieved: list[list[dict]], gate: LLMGate
) -> dict:
    if gate.allowed():
        try:
            parsed = llm_analyze(text, jd_title, requirements, retrieved)
            gate.record(True)
            return finalize_analysis(parsed, text, filename, requirements, "llm")
        except Exception as e:  # noqa: BLE001
            gate.record(False)
            logger.warning("LLM analysis failed for %s, using heuristic fallback: %s", filename, e)
    parsed = heuristic_analyze(text, requirements, retrieved)
    return finalize_analysis(parsed, text, filename, requirements, "heuristic")


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------
_active_runs: set[str] = set()
_active_lock = threading.Lock()


def is_running(session_id: str) -> bool:
    with _active_lock:
        return session_id in _active_runs


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or datetime.now(timezone.utc)).isoformat()


class _Progress:
    """Writes pipeline progress into SessionRun (own DB session, main pipeline thread only)."""

    def __init__(self, db: Any, session_id: str) -> None:
        self.db = db
        self.session_id = session_id
        self.steps = {k: {"key": k, "label": label, "status": "pending", "at": None} for k, label in STEP_DEFS}
        self.eta: Optional[int] = None

    def run(self) -> SessionRun:
        run = self.db.get(SessionRun, self.session_id)
        if run is None:
            run = SessionRun(session_id=self.session_id)
            self.db.add(run)
            self.db.flush()
        return run

    def set_step(self, key: str, status: str) -> None:
        self.steps[key]["status"] = status
        self.steps[key]["at"] = _iso()

    def push(self, stage: str, percent: float, processed: Optional[int] = None, total: Optional[int] = None) -> None:
        run = self.run()
        run.stage = stage
        run.percent = round(min(100.0, max(0.0, percent)), 1)
        if processed is not None:
            run.processed = processed
        if total is not None:
            run.total = total
        run.activity = {"steps": [self.steps[k] for k, _ in STEP_DEFS], "eta_seconds": self.eta}
        run.updated_at = get_utc_now()
        self.db.commit()


def start_pipeline(session_id: str) -> bool:
    """Start the background pipeline. Returns False if one is already running for this session."""
    with _active_lock:
        if session_id in _active_runs:
            return False
        _active_runs.add(session_id)
    threading.Thread(target=_run_wrapper, args=(session_id,), daemon=True, name=f"screening-{session_id[:8]}").start()
    return True


def _run_wrapper(session_id: str) -> None:
    try:
        _run_pipeline(session_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("Screening pipeline crashed for %s", session_id)
        db = SessionLocal()
        try:
            run = db.get(SessionRun, session_id)
            if run is not None:
                run.status = "failed"
                run.error = f"Pipeline error: {str(e)[:300]}"
                run.finished_at = get_utc_now()
                db.commit()
        finally:
            db.close()
    finally:
        with _active_lock:
            _active_runs.discard(session_id)


def _failed_result(filename: str, reason: str) -> dict:
    return {
        "candidate_name": guess_name("", filename),
        "email": None,
        "experience_years": None,
        "skills": [],
        "requirement_results": [],
        "matched": [],
        "partial": [],
        "missing": [],
        "highlights": [],
        "projects": [],
        "experience": [],
        "assessment": reason,
        "match_percent": 0.0,
        "tier": "low",
        "scoring_mode": None,
        "status": "failed",
        "error": reason[:500],
    }


def _upsert_result(db: Any, session_id: str, resume_id: str, filename: str, data: dict) -> None:
    row = (
        db.query(CandidateResult)
        .filter(CandidateResult.session_id == session_id, CandidateResult.resume_id == resume_id)
        .first()
    )
    if row is None:
        row = CandidateResult(session_id=session_id, resume_id=resume_id, original_filename=filename)
        db.add(row)
    row.original_filename = filename
    row.candidate_name = data["candidate_name"]
    row.email = data.get("email")
    row.experience_years = data.get("experience_years")
    row.skills = data["skills"]
    row.match_percent = data["match_percent"]
    row.tier = data["tier"]
    row.requirement_results = data["requirement_results"]
    row.matched = data["matched"]
    row.partial = data["partial"]
    row.missing = data["missing"]
    row.highlights = data["highlights"]
    row.projects = data["projects"]
    row.experience = data["experience"]
    row.assessment = data["assessment"]
    row.scoring_mode = data.get("scoring_mode")
    row.status = data.get("status", "scored")
    row.error = data.get("error")
    row.updated_at = get_utc_now()


def _run_pipeline(session_id: str) -> None:
    db = SessionLocal()
    prog = _Progress(db, session_id)
    t_start = time.time()
    try:
        session = db.get(ScreeningSession, session_id)
        if session is None:
            return
        jd = session.job_description
        run = prog.run()
        run.status = "running"
        run.error = None
        run.started_at = get_utc_now()
        run.finished_at = None
        run.processed = 0
        prog.eta = None
        db.commit()

        done_ids = {
            rid for (rid,) in db.query(CandidateResult.resume_id).filter(CandidateResult.session_id == session_id).all()
        }
        resumes = (
            db.query(StagedResume)
            .filter(StagedResume.screening_session_id == session_id)
            .order_by(StagedResume.created_at.asc())
            .all()
        )
        pending = [r for r in resumes if r.id not in done_ids]

        session_dir = RESUME_STORAGE_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # ---------------- Step 1: extract text (ZIP -> one candidate per member) ----------------
        prog.set_step("extract", "running")
        prog.push("extract", 2, 0, len(pending))

        for r in list(pending):
            if r.file_type != ".zip":
                continue
            status, members, err = extract_zip_members(RESUME_STORAGE_DIR / r.storage_name)
            if status == "extracted":
                for fname, ext, text in members:
                    child = StagedResume(
                        screening_session_id=session_id,
                        original_filename=fname,
                        file_type=ext,
                        file_size=len(text.encode("utf-8")),
                        storage_name=f"member:{uuid.uuid4().hex}",
                        extraction_status="extracted",
                    )
                    db.add(child)
                    db.flush()
                    (session_dir / f"{child.id}.txt").write_text(text, encoding="utf-8")
                    pending.append(child)
                try:
                    (RESUME_STORAGE_DIR / r.storage_name).unlink(missing_ok=True)
                except OSError:
                    pass
                pending.remove(r)
                db.delete(r)
            else:
                r.extraction_status = status
                r.extraction_error = err
        db.commit()

        texts: dict[str, str] = {}
        failed: list[tuple[StagedResume, str]] = []
        for i, r in enumerate(pending):
            txt_path = session_dir / f"{r.id}.txt"
            if r.extraction_status != "extracted" or not txt_path.exists():
                if r.extraction_status in ("pending", "extracted"):
                    status, text, err = extract_resume_text(RESUME_STORAGE_DIR / r.storage_name, r.file_type)
                    r.extraction_status, r.extraction_error = status, err
                    if status == "extracted":
                        txt_path.write_text(text, encoding="utf-8")
            if r.extraction_status == "extracted" and txt_path.exists():
                texts[r.id] = txt_path.read_text(encoding="utf-8", errors="replace")
            else:
                failed.append((r, r.extraction_error or f"Text extraction {r.extraction_status}."))
            prog.push("extract", 2 + 13 * (i + 1) / max(len(pending), 1))
        db.commit()
        prog.set_step("extract", "done")

        total = len(pending)
        processed = 0
        for r, reason in failed:
            _upsert_result(db, session_id, r.id, r.original_filename, _failed_result(r.original_filename, reason))
            processed += 1
        db.commit()
        prog.push("embed", 15, processed, total)

        to_process = [r for r in pending if r.id in texts]

        # ---------------- Step 2: embeddings ----------------
        provider = None
        model_name = "nomic-embed-text"
        embeddings: dict[str, tuple[list[dict], list[list[float]]]] = {}
        embeddings_ok = True
        warning: Optional[str] = None
        prog.set_step("embed", "running")
        prog.push("embed", 15, processed, total)
        try:
            provider = get_embedding_provider()
            model_name = getattr(provider, "model_name", model_name)
            chunker = TextChunker()
            for i, r in enumerate(to_process):
                chunks = chunker.chunk_text(texts[r.id])
                vecs = provider.embed_documents([c["text"] for c in chunks]) if chunks else []
                embeddings[r.id] = (chunks, vecs)
                prog.push("embed", 15 + 20 * (i + 1) / max(len(to_process), 1))
        except Exception as e:  # noqa: BLE001
            embeddings_ok = False
            warning = f"Embeddings unavailable ({str(e)[:160]}). Scoring used full resume text."
            logger.warning(warning)
        prog.set_step("embed", "done")

        # ---------------- Step 3: vector store ----------------
        prog.set_step("store", "running")
        prog.push("store", 35, processed, total)
        if embeddings_ok:
            for i, r in enumerate(to_process):
                chunks, vecs = embeddings.get(r.id, ([], []))
                try:
                    n = store_chunks(session_id, r.id, r.original_filename, chunks, vecs, model_name) if vecs else 0
                    r.indexing_status = "indexed" if n else "skipped"
                    r.index_model = model_name
                    r.chunk_count = n
                    r.indexing_error = None
                except Exception as e:  # noqa: BLE001
                    r.indexing_status = "failed"
                    r.indexing_error = str(e)[:300]
                prog.push("store", 35 + 5 * (i + 1) / max(len(to_process), 1))
            try:
                cleanup_old_collections(session_id, active_model_name=model_name)
            except Exception:  # noqa: BLE001
                pass
            db.commit()
        prog.set_step("store", "done")

        # ---------------- Step 4: evaluate ----------------
        prog.set_step("evaluate", "running")
        prog.push("evaluate", 40, processed, total)

        requirements = list(run.requirements or [])
        if not requirements:
            requirements = build_requirements(jd)
            run.requirements = requirements
            db.commit()

        q_emb: list[list[float]] = []
        col = None
        if embeddings_ok and provider is not None:
            try:
                q_emb = [provider.embed_query(r["query"]) for r in requirements]
                col = get_session_collection(session_id, model_name=model_name)
            except Exception as e:  # noqa: BLE001
                warning = f"Requirement embedding failed ({str(e)[:120]}). Scoring used full resume text."
                q_emb, col = [], None

        gate = LLMGate()
        eval_started = time.time()
        jd_title = jd.title
        names = {r.id: r.original_filename for r in to_process}

        # NOTE: worker threads receive plain values only (never ORM objects bound to this DB session).
        def work(resume_id: str, filename: str, text: str, retrieved: list[list[dict]]) -> tuple[str, dict]:
            try:
                data = analyze_candidate(text, filename, jd_title, requirements, retrieved, gate)
                data["status"] = "scored"
                data["error"] = None
                return resume_id, data
            except Exception as e:  # noqa: BLE001
                logger.exception("Candidate analysis failed for %s", filename)
                return resume_id, _failed_result(filename, f"Analysis failed: {str(e)[:200]}")

        done_eval = 0
        with ThreadPoolExecutor(max_workers=SCREENING_CONCURRENCY) as pool:
            futures = []
            for rid, fname in names.items():
                retrieved = retrieve_for_resume(col, rid, q_emb, top_k=2) if (col is not None and q_emb) else []
                futures.append(pool.submit(work, rid, fname, texts[rid], retrieved))
            for fut in as_completed(futures):
                rid, data = fut.result()
                _upsert_result(db, session_id, rid, names[rid], data)
                db.commit()
                processed += 1
                done_eval += 1
                elapsed = time.time() - eval_started
                remaining = max(len(to_process) - done_eval, 0)
                prog.eta = int(elapsed / done_eval * remaining) if done_eval else None
                prog.push("evaluate", 40 + 55 * done_eval / max(len(to_process), 1), processed, total)
        prog.set_step("evaluate", "done")

        # ---------------- Step 5: finish ----------------
        prog.set_step("prepare", "running")
        prog.eta = 0
        prog.push("prepare", 97, processed, total)
        modes = {
            m
            for (m,) in db.query(CandidateResult.scoring_mode)
            .filter(CandidateResult.session_id == session_id, CandidateResult.status == "scored")
            .all()
            if m
        }
        run = prog.run()
        run.scoring_mode = "mixed" if len(modes) > 1 else (next(iter(modes)) if modes else None)
        session.updated_at = get_utc_now()
        prog.set_step("prepare", "done")
        run.status = "completed"
        run.error = warning
        run.finished_at = get_utc_now()
        prog.push("done", 100, processed, total)
        logger.info("Screening %s finished in %.1fs", session_id, time.time() - t_start)
    finally:
        db.close()
