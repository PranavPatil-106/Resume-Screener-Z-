import json
import logging
import os
import re
import math
import shutil
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Depends, File, UploadFile, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy.orm import Session, joinedload

from database import (
    get_db,
    engine,
    DATABASE_URL,
    RESUME_STORAGE_DIR,
    MAX_FILE_SIZE_BYTES,
    MAX_BATCH_SIZE_BYTES,
    ALLOWED_EXTENSIONS,
    AUTH_COOKIE_NAME,
    AUTH_COOKIE_SECURE,
    SESSION_MAX_AGE_SECONDS,
    INVITATION_MAX_AGE_SECONDS,
)
from models import (
    JobDescription,
    ScreeningSession,
    StagedResume,
    ResumeEvaluation,
    CandidateResult,
    SessionRun,
    User,
    UserSession,
    UserInvitation,
    UserRole,
    UserStatus,
    SessionStatus,
    get_utc_now,
)
from schemas import (
    JobDescriptionCreate,
    JobDescriptionUpdate,
    JobDescriptionResponse,
    ScreeningSessionCreate,
    ScreeningSessionResponse,
    DraftScreeningSessionResponse,
    StagedResumeResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
    SearchResultItem,
    EvidenceChatRequest,
    EvidenceChatResponse,
    LLMStatusResponse,
    SystemStatusResponse,
    ResumeEvaluationResponse,
    CandidateEvaluationDirectoryItem,
    RubricCriterionItem,
    LoginRequest,
    LogoutResponse,
    UserResponse,
    InviteUserRequest,
    InviteUserResponse,
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    UpdateUserRoleRequest,
    UpdateUserStatusRequest,
    RetrievedEvidenceChunk,
    CriterionEvidenceGroup,
    ResumeBatchRetrievalItem,
    BatchRetrievalJobDescriptionSummary,
    BatchEvidenceRetrievalRequest,
    BatchEvidenceRetrievalResponse,
)
from password_security import (
    verify_password,
    hash_password,
    generate_session_token,
    hash_session_token,
    generate_invitation_token,
    hash_invitation_token,
)
from text_extractor import extract_resume_text
from chunker import TextChunker
from embedding_provider import get_embedding_provider, EmbeddingModelSetupError
from llm_provider import get_llm_provider, LLMProviderDisabledError
from vector_store import (
    index_resume_chunks,
    search_session,
    batch_search_criteria_for_resume,
    delete_resume_from_index,
    close_session_chroma,
    remove_session_storage_dir,
    cleanup_old_collections,
)

app = FastAPI(
    title="AI Resume Screener API",
    version="0.1.0",
)

logger = logging.getLogger(__name__)


def verify_quote_against_source(quote: str, source_text: str) -> bool:
    """
    Validates whether an evidence quote actually matches text in the extracted resume.
    Checks exact stripped substring, case-insensitive substring, and normalized-whitespace substring.
    Rejects empty quotes or quotes not supported by the source text.
    """
    if not isinstance(quote, str):
        return False
    cleaned_quote = quote.strip()
    if not cleaned_quote:
        return False

    # 1. Exact substring match
    if cleaned_quote in source_text:
        return True

    # 2. Case-insensitive substring match
    if cleaned_quote.lower() in source_text.lower():
        return True

    # 3. Normalized whitespace match (handles line-wrapping or multi-space variations)
    def normalize_ws(t: str) -> str:
        return " ".join(t.split()).lower()

    if normalize_ws(cleaned_quote) in normalize_ws(source_text):
        return True

    return False

# Configure exact frontend origins for local development and credentials support
cors_origins_env = os.getenv("CORS_ORIGINS")
if cors_origins_env:
    cors_origins = [orig.strip() for orig in cors_origins_env.split(",") if orig.strip() and orig.strip() != "*"]
else:
    cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "AI Resume Screener API",
    }


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """
    Authenticate request via session token stored in HTTP-only cookie.
    Validates token hash, expiration, revocation, and active user status.
    """
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token_hash = hash_session_token(token)
    session = (
        db.query(UserSession)
        .options(joinedload(UserSession.user))
        .filter(UserSession.token_hash == token_hash)
        .first()
    )

    if not session or not session.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    if not session.user or session.user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    return session.user


def require_roles(*allowed_roles: str):
    """
    Reusable FastAPI dependency factory for role-based authorization.
    Verifies authentication via get_current_user first (returning 401 if unauthenticated),
    then checks whether the authenticated user has one of the allowed roles (returning 403 if forbidden).
    Does not leak whether another user or session exists when authorization fails.
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted",
            )
        return current_user

    return role_checker


require_admin_only = require_roles(UserRole.ADMIN.value)
require_admin_or_recruiter = require_roles(UserRole.ADMIN.value, UserRole.RECRUITER.value)
require_any_authenticated_user = require_roles(
    UserRole.ADMIN.value,
    UserRole.RECRUITER.value,
    UserRole.VIEWER.value,
)

# --- Screening workflow (background pipeline, results, candidate detail, chat, JD parsing, dashboard) ---
from screening_api import build_router, candidate_directory_items, candidate_result_as_evaluation  # noqa: E402

# shortcut: the two new tables are created at startup instead of via an Alembic migration; add a migration before production.
SessionRun.__table__.create(bind=engine, checkfirst=True)
CandidateResult.__table__.create(bind=engine, checkfirst=True)

app.include_router(build_router(require_admin_or_recruiter, require_any_authenticated_user, require_admin_only))


@app.post("/api/auth/login", response_model=UserResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Authenticate user via email and password, create persisted session,
    and set HTTP-only cookie with opaque session token.
    Returns generic 401 on invalid credentials or inactive user.
    """
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()

    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Generate opaque random session token and store SHA-256 hash in DB
    raw_token = generate_session_token()
    token_hash = hash_session_token(raw_token)
    expires_at = get_utc_now() + timedelta(seconds=SESSION_MAX_AGE_SECONDS)

    session = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()

    # Set HTTP-only, SameSite=Lax cookie with the raw session token
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=raw_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=AUTH_COOKIE_SECURE,
        path="/",
    )

    return user


@app.post("/api/auth/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Revoke current session in the database and clear the authentication cookie.
    """
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        token_hash = hash_session_token(token)
        session = db.query(UserSession).filter(UserSession.token_hash == token_hash).first()
        if session and session.revoked_at is None:
            session.revoked_at = get_utc_now()
            db.commit()

    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=AUTH_COOKIE_SECURE,
    )
    return LogoutResponse(message="Logged out successfully")


@app.get("/api/auth/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user),
):
    """
    Return currently authenticated user information using UserResponse.
    Never exposes password hashes or session tokens.
    """
    return current_user


@app.get("/api/users", response_model=list[UserResponse])
def list_users(
    current_user: User = Depends(require_admin_only),
    db: Session = Depends(get_db),
):
    """
    Retrieve all users in the system. Accessible exclusively to administrators.
    Returns user directory using UserResponse schema; never exposes password hashes
    or session tokens.
    """
    return db.query(User).order_by(User.created_at.asc()).all()


@app.patch("/api/users/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: str,
    payload: UpdateUserRoleRequest,
    current_user: User = Depends(require_admin_only),
    db: Session = Depends(get_db),
):
    """
    Update a user's assigned role. Exclusively accessible to administrators.
    Accepts only admin, recruiter, or viewer.
    Returns 404 for missing users and 403 for non-admin callers.
    Transactionally guards against demoting the last active administrator.
    Never returns credentials or token hashes.
    Does not alter account status, sessions, or invitation behavior.
    """
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    new_role = payload.role.value if hasattr(payload.role, "value") else str(payload.role)

    # Guard: prevent demoting the last active administrator
    if (
        target_user.role == UserRole.ADMIN.value
        and target_user.status == UserStatus.ACTIVE.value
        and new_role != UserRole.ADMIN.value
    ):
        active_admins_query = db.query(User).filter(
            User.role == UserRole.ADMIN.value,
            User.status == UserStatus.ACTIVE.value,
        )
        try:
            if db.get_bind().dialect.name != "sqlite":
                active_admins_query = active_admins_query.with_for_update()
        except Exception:
            pass

        active_admin_count = active_admins_query.count()
        if active_admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last active administrator.",
            )

    if target_user.role != new_role:
        target_user.role = new_role
        target_user.updated_at = get_utc_now()
        db.commit()
        db.refresh(target_user)

    return target_user


@app.patch("/api/users/{user_id}/status", response_model=UserResponse)
def update_user_status(
    user_id: str,
    payload: UpdateUserStatusRequest,
    current_user: User = Depends(require_admin_only),
    db: Session = Depends(get_db),
):
    """
    Update a user's account status (active or disabled). Exclusively accessible to administrators.
    - Accepts only 'active' or 'disabled'.
    - Rejects activating or disabling invited accounts (invitations must be accepted or revoked).
    - When disabling an active user, revokes all unrevoked login sessions and pending invitations
      in the same transaction.
    - Prevents an Admin from disabling themself or disabling the last active Admin.
    - Allows reactivation only for previously disabled accounts that possess a password hash.
    - Preserves user roles, passwords, and authorization policies.
    - Returns sanitized UserResponse; preserves generic 401/403 authorization behavior.
    """
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    target_status = payload.status.value if hasattr(payload.status, "value") else str(payload.status)

    # Do not allow this endpoint to activate an invited account
    if target_user.status == UserStatus.INVITED.value:
        if target_status == UserStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot activate an invited account directly. The user must accept their invitation.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status changes are not permitted for invited accounts.",
        )

    now = get_utc_now()

    if target_status == UserStatus.DISABLED.value:
        if target_user.status == UserStatus.DISABLED.value:
            return target_user

        # Prevent an Admin from disabling themself
        if target_user.id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Administrators cannot disable their own account.",
            )

        # Prevent disabling the last active Admin (transactional, SQLite & PostgreSQL compatible)
        if target_user.role == UserRole.ADMIN.value:
            active_admins_query = db.query(User).filter(
                User.role == UserRole.ADMIN.value,
                User.status == UserStatus.ACTIVE.value,
            )
            try:
                if db.get_bind().dialect.name != "sqlite":
                    active_admins_query = active_admins_query.with_for_update()
            except Exception:
                pass

            active_admin_count = active_admins_query.count()
            if active_admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot disable the last active administrator.",
                )

        # Revoke unrevoked login sessions and pending invitations in the same transaction
        unrevoked_sessions = (
            db.query(UserSession)
            .filter(
                UserSession.user_id == target_user.id,
                UserSession.revoked_at.is_(None),
            )
            .all()
        )
        for s in unrevoked_sessions:
            s.revoked_at = now

        pending_invitations = (
            db.query(UserInvitation)
            .filter(
                UserInvitation.user_id == target_user.id,
                UserInvitation.accepted_at.is_(None),
                UserInvitation.revoked_at.is_(None),
            )
            .all()
        )
        for inv in pending_invitations:
            inv.revoked_at = now

        target_user.status = UserStatus.DISABLED.value
        target_user.updated_at = now
        db.commit()
        db.refresh(target_user)

    elif target_status == UserStatus.ACTIVE.value:
        if target_user.status == UserStatus.ACTIVE.value:
            return target_user

        # Allow reactivation only for a previously disabled account that has a password hash
        if not target_user.password_hash or not target_user.password_hash.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot reactivate an account without a password hash.",
            )

        target_user.status = UserStatus.ACTIVE.value
        target_user.updated_at = now
        db.commit()
        db.refresh(target_user)

    return target_user



@app.post(
    "/api/users/invite",
    response_model=InviteUserResponse,
    status_code=status.HTTP_201_CREATED,
)
def invite_user(
    payload: InviteUserRequest,
    current_user: User = Depends(require_admin_only),
    db: Session = Depends(get_db),
):
    """
    Invite a user with an assigned role. Exclusively accessible to administrators.
    Creates a user with status='invited', generates a one-time cryptographically secure
    invitation token returned exactly once, and persists only the SHA-256 token hash.
    No emails are sent or logged. The invitation token must be communicated manually
    over a secure channel because email delivery is not configured.
    If an unaccepted invitation already exists for an invited user, it is safely revoked
    and replaced with a fresh invitation.
    """
    normalized_email = payload.email.strip().lower()
    if not normalized_email or "@" not in normalized_email or "." not in normalized_email.split("@")[-1]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email format. Please provide a valid email address.",
        )

    existing_user = db.query(User).filter(User.email == normalized_email).first()
    now = get_utc_now()

    role_value = payload.role.value if hasattr(payload.role, "value") else str(payload.role)

    if existing_user:
        if existing_user.status == UserStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email address already exists and is active.",
            )
        # Safely revoke existing unaccepted invitations for this user before issuing a fresh one
        unaccepted_invitations = (
            db.query(UserInvitation)
            .filter(
                UserInvitation.user_id == existing_user.id,
                UserInvitation.accepted_at.is_(None),
                UserInvitation.revoked_at.is_(None),
            )
            .all()
        )
        for inv in unaccepted_invitations:
            inv.revoked_at = now

        existing_user.role = role_value
        existing_user.updated_at = now
        user = existing_user
    else:
        user = User(
            email=normalized_email,
            role=role_value,
            status=UserStatus.INVITED.value,
            password_hash=None,
        )
        db.add(user)
        db.flush()

    raw_token = generate_invitation_token()
    token_hash = hash_invitation_token(raw_token)
    expires_at = now + timedelta(seconds=INVITATION_MAX_AGE_SECONDS)

    invitation = UserInvitation(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        created_by_id=current_user.id,
    )
    db.add(invitation)
    db.commit()
    db.refresh(user)

    return InviteUserResponse(
        user=user,
        invitation_token=raw_token,
        expires_at=expires_at,
        message=(
            "User invitation created. The invitation token must be shared manually with the user "
            "through a secure channel because email delivery is not configured."
        ),
    )


@app.post("/api/auth/accept-invitation", response_model=AcceptInvitationResponse)
def accept_invitation(
    payload: AcceptInvitationRequest,
    db: Session = Depends(get_db),
):
    """
    Public endpoint to consume an invitation token and activate a user account.
    Validates token expiry and single-use, hashes the candidate password using Argon2id,
    marks the user active, and consumes the invitation.
    Returns generic errors on invalid, expired, or consumed tokens to prevent token enumeration.
    Never exposes password hashes or token hashes.
    """
    token_str = payload.token.strip()
    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or consumed invitation token",
        )

    if len(payload.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long",
        )

    token_hash = hash_invitation_token(token_str)
    invitation = (
        db.query(UserInvitation)
        .options(joinedload(UserInvitation.user))
        .filter(UserInvitation.token_hash == token_hash)
        .first()
    )

    if not invitation or not invitation.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or consumed invitation token",
        )

    user = invitation.user
    if not user or user.status != UserStatus.INVITED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or consumed invitation token",
        )

    pw_hash = hash_password(payload.password)
    now = get_utc_now()

    user.password_hash = pw_hash
    user.status = UserStatus.ACTIVE.value
    user.updated_at = now

    invitation.accepted_at = now

    # Safely revoke any other pending invitations for this user
    other_pending = (
        db.query(UserInvitation)
        .filter(
            UserInvitation.user_id == user.id,
            UserInvitation.id != invitation.id,
            UserInvitation.accepted_at.is_(None),
            UserInvitation.revoked_at.is_(None),
        )
        .all()
    )
    for other_inv in other_pending:
        other_inv.revoked_at = now

    db.commit()
    db.refresh(user)

    return AcceptInvitationResponse(
        message="Invitation accepted successfully. Account is now active.",
        user=user,
    )


@app.get("/api/job-descriptions", response_model=list[JobDescriptionResponse])
def list_job_descriptions(
    include_archived: bool = True,
    current_user: User = Depends(require_any_authenticated_user),
    db: Session = Depends(get_db),
):
    """Retrieve all stored job descriptions ordered by newest first."""
    query = db.query(JobDescription)
    if not include_archived:
        query = query.filter(JobDescription.is_archived.is_(False))
    return query.order_by(JobDescription.created_at.desc()).all()


@app.post(
    "/api/job-descriptions",
    response_model=JobDescriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_job_description(
    payload: JobDescriptionCreate,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """Create and persist a new job description."""
    skills_list = payload.skills or payload.tags or []
    new_jd = JobDescription(
        title=payload.title,
        category=payload.category,
        description=payload.description,
        skills=skills_list,
        experience=payload.experience,
        employment_type=payload.employment_type,
    )
    db.add(new_jd)
    db.commit()
    db.refresh(new_jd)
    return new_jd


@app.put(
    "/api/job-descriptions/{jd_id}",
    response_model=JobDescriptionResponse,
)
def update_job_description(
    jd_id: str,
    payload: JobDescriptionUpdate,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """Update an existing job description."""
    jd = db.query(JobDescription).filter(JobDescription.id == jd_id).first()
    if not jd:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job description with ID '{jd_id}' not found.",
        )
    skills_list = payload.skills or payload.tags or []
    jd.title = payload.title
    jd.category = payload.category
    jd.description = payload.description
    jd.skills = skills_list
    jd.experience = payload.experience
    jd.employment_type = payload.employment_type
    jd.updated_at = get_utc_now()
    db.commit()
    db.refresh(jd)
    return jd


@app.post(
    "/api/job-descriptions/{jd_id}/archive",
    response_model=JobDescriptionResponse,
)
def archive_job_description(
    jd_id: str,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """Soft-archive a Job Description."""
    jd = db.query(JobDescription).filter(JobDescription.id == jd_id).first()
    if not jd:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job description with ID '{jd_id}' not found.",
        )
    jd.is_archived = True
    jd.archived_at = get_utc_now()
    jd.updated_at = get_utc_now()
    db.commit()
    db.refresh(jd)
    return jd


@app.post(
    "/api/job-descriptions/{jd_id}/restore",
    response_model=JobDescriptionResponse,
)
def restore_job_description(
    jd_id: str,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """Restore a soft-archived Job Description."""
    jd = db.query(JobDescription).filter(JobDescription.id == jd_id).first()
    if not jd:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job description with ID '{jd_id}' not found.",
        )
    jd.is_archived = False
    jd.archived_at = None
    jd.updated_at = get_utc_now()
    db.commit()
    db.refresh(jd)
    return jd


@app.get("/api/screening-sessions", response_model=list[ScreeningSessionResponse])
def list_screening_sessions(
    current_user: User = Depends(require_any_authenticated_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve all screening sessions with their Job Description title ordered by newest first.
    Admin and recruiter users access all sessions.
    Viewer users are restricted to completed screening session metadata only.
    """
    query = (
        db.query(ScreeningSession)
        .options(joinedload(ScreeningSession.job_description))
        .order_by(ScreeningSession.created_at.desc())
    )
    if current_user.role == UserRole.VIEWER.value:
        query = query.filter(ScreeningSession.status == "completed")
    return query.all()


@app.post(
    "/api/screening-sessions",
    response_model=ScreeningSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_screening_session(
    payload: ScreeningSessionCreate,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """Create a new draft screening session linked to a Job Description."""
    jd = (
        db.query(JobDescription)
        .filter(JobDescription.id == payload.job_description_id)
        .first()
    )
    if not jd:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job description with ID '{payload.job_description_id}' not found.",
        )
    if jd.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot create a screening session with an archived Job Description ('{jd.title}').",
        )

    new_session = ScreeningSession(
        job_description_id=payload.job_description_id,
        status="draft",
    )
    db.add(new_session)
    db.flush()
    db.add(
        SessionRun(
            session_id=new_session.id,
            created_by_email=current_user.email,
            status="idle",
            activity={},
            requirements=[],
            chat_state={},
        )
    )
    db.commit()
    db.refresh(new_session)
    return new_session


@app.get(
    "/api/screening-sessions/{session_id}",
    response_model=DraftScreeningSessionResponse,
    summary="Get draft screening session detail with linked JD and staged resumes",
)
def get_draft_screening_session(
    session_id: str,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """
    Retrieve one draft screening session by ID with its linked Job Description metadata
    and staged resume metadata. Accessible exclusively to Admins and Recruiters.
    Rejects ended or non-draft sessions with HTTP 409 Conflict.
    Returns only metadata; never exposes resume text, file bytes, storage paths, or vector contents.
    """
    session = (
        db.query(ScreeningSession)
        .options(
            joinedload(ScreeningSession.job_description),
            joinedload(ScreeningSession.resumes),
            joinedload(ScreeningSession.evaluations),
        )
        .filter(ScreeningSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening session '{session_id}' not found.",
        )

    if session.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Screening session '{session_id}' is in '{session.status}' status. "
                "Only draft sessions can be reopened."
            ),
        )

    # Check for model mismatch on indexed draft resumes
    try:
        active_model = getattr(get_embedding_provider(), "model_name", "nomic-embed-text")
        for r in session.resumes:
            if r.indexing_status == "indexed" and (not r.index_model or r.index_model != active_model):
                r.indexing_status = "needs_reindex"
                r.indexing_error = (
                    f"Model mismatch: indexed with '{r.index_model or 'legacy/bge'}', "
                    f"active model is '{active_model}'. Re-indexing required."
                )
    except Exception:
        pass

    return session


@app.post(
    "/api/screening-sessions/{session_id}/resumes",
    response_model=list[StagedResumeResponse],
    status_code=status.HTTP_201_CREATED,
)
async def stage_resumes(
    session_id: str,
    files: list[UploadFile] = File(...),
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """
    Stream and stage resume files for an existing draft screening session.
    Enforces allowed file extensions (.pdf, .doc, .docx, .zip) and size limits.
    Files are stored in local temporary storage and only metadata is persisted.
    Cleans up any written files on batch failure.
    """
    session = (
        db.query(ScreeningSession)
        .filter(ScreeningSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening session '{session_id}' not found.",
        )

    if session.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Screening session '{session_id}' is in '{session.status}' status. "
                "Resumes can only be staged for sessions in 'draft' status."
            ),
        )

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided in upload batch.",
        )

    # 1. Validate all extensions first before streaming any file to disk
    for file in files:
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            allowed_list = ", ".join(sorted(ALLOWED_EXTENSIONS))
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=(
                    f"Unsupported file type '{ext}' for file '{file.filename}'. "
                    f"Allowed file types are: {allowed_list}"
                ),
            )

    # 2. Stream files to temporary storage, tracking file size and total batch size
    saved_paths: list[Path] = []
    staged_records: list[StagedResume] = []
    total_batch_size = 0

    try:
        for file in files:
            ext = Path(file.filename or "").suffix.lower()
            storage_name = f"{uuid.uuid4().hex}{ext}"
            destination_path = RESUME_STORAGE_DIR / storage_name
            saved_paths.append(destination_path)

            file_size = 0
            with open(destination_path, "wb") as buffer:
                while chunk := await file.read(64 * 1024):
                    file_size += len(chunk)
                    if file_size > MAX_FILE_SIZE_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=(
                                f"File '{file.filename}' ({file_size} bytes) exceeds the maximum allowed "
                                f"per-file limit of {MAX_FILE_SIZE_BYTES} bytes ({MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB)."
                            ),
                        )
                    total_batch_size += len(chunk)
                    if total_batch_size > MAX_BATCH_SIZE_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=(
                                f"Total upload batch exceeds the maximum allowed batch limit of "
                                f"{MAX_BATCH_SIZE_BYTES} bytes ({MAX_BATCH_SIZE_BYTES // (1024 * 1024)} MB)."
                            ),
                        )
                    buffer.write(chunk)

            staged_records.append(
                StagedResume(
                    screening_session_id=session_id,
                    original_filename=file.filename or "unknown",
                    file_type=ext,
                    file_size=file_size,
                    storage_name=storage_name,
                    extraction_status="pending",
                    extraction_error=None,
                )
            )

        db.add_all(staged_records)
        session.updated_at = get_utc_now()
        db.commit()
        for rec in staged_records:
            db.refresh(rec)
        return staged_records

    except Exception:
        # Atomic cleanup: remove any files written to disk during this failed batch
        for path in saved_paths:
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
        raise


@app.get(
    "/api/screening-sessions/{session_id}/resumes",
    response_model=list[StagedResumeResponse],
)
def get_session_resumes(
    session_id: str,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """Retrieve staged resume metadata for a specific screening session."""
    session = (
        db.query(ScreeningSession)
        .filter(ScreeningSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening session '{session_id}' not found.",
        )

    resumes = (
        db.query(StagedResume)
        .filter(StagedResume.screening_session_id == session_id)
        .order_by(StagedResume.created_at.asc())
        .all()
    )

    if session.status == "draft":
        try:
            active_model = getattr(get_embedding_provider(), "model_name", "nomic-embed-text")
            for r in resumes:
                if r.indexing_status == "indexed" and (not r.index_model or r.index_model != active_model):
                    r.indexing_status = "needs_reindex"
                    r.indexing_error = (
                        f"Model mismatch: indexed with '{r.index_model or 'legacy/bge'}', "
                        f"active model is '{active_model}'. Re-indexing required."
                    )
        except Exception:
            pass

    return resumes


@app.post(
    "/api/screening-sessions/{session_id}/extract-text",
    response_model=list[StagedResumeResponse],
)
def extract_session_text(
    session_id: str,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """
    Extract text from staged resume files for an existing draft screening session.
    PDF and DOCX files are extracted directly. ZIP archives are inspected in memory
    for supported PDF and DOCX members without filesystem extraction. Extraction of
    legacy .doc files requires a free local converter such as LibreOffice or Antiword.
    Stores extracted text as temporary files in the session's temporary storage directory,
    keyed by staged resume ID, and updates extraction status and error messages in metadata.
    """
    session = (
        db.query(ScreeningSession)
        .filter(ScreeningSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening session '{session_id}' not found.",
        )

    if session.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Screening session '{session_id}' is in '{session.status}' status. "
                "Text extraction can only be performed on sessions in 'draft' status."
            ),
        )

    resumes = (
        db.query(StagedResume)
        .filter(StagedResume.screening_session_id == session_id)
        .order_by(StagedResume.created_at.asc())
        .all()
    )

    session_storage_dir = RESUME_STORAGE_DIR / session_id
    session_storage_dir.mkdir(parents=True, exist_ok=True)

    for resume in resumes:
        file_path = RESUME_STORAGE_DIR / resume.storage_name
        ext_status, extracted_text, ext_err = extract_resume_text(
            file_path=file_path,
            file_type=resume.file_type,
        )

        extracted_file_path = session_storage_dir / f"{resume.id}.txt"

        if ext_status == "extracted":
            extracted_file_path.write_text(extracted_text, encoding="utf-8")
        else:
            # Clean up any previously extracted text file if status is empty, failed, or unsupported
            if extracted_file_path.exists():
                try:
                    extracted_file_path.unlink()
                except OSError:
                    pass

        resume.extraction_status = ext_status
        resume.extraction_error = ext_err
        resume.updated_at = get_utc_now()

    session.updated_at = get_utc_now()
    db.commit()
    for resume in resumes:
        db.refresh(resume)

    return resumes


@app.delete(
    "/api/screening-sessions/{session_id}/resumes/{resume_id}",
    status_code=status.HTTP_200_OK,
)
def delete_staged_resume(
    session_id: str,
    resume_id: str,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """
    Remove one staged resume by its metadata ID:
    unlinks the temporary original file and any extracted text file from disk,
    and deletes the database record.
    """
    session = (
        db.query(ScreeningSession)
        .filter(ScreeningSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening session '{session_id}' not found.",
        )

    if session.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Screening session '{session_id}' is in '{session.status}' status. "
                "Resumes can only be modified for sessions in 'draft' status."
            ),
        )

    resume = (
        db.query(StagedResume)
        .filter(
            StagedResume.id == resume_id,
            StagedResume.screening_session_id == session_id,
        )
        .first()
    )
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Staged resume '{resume_id}' not found in screening session '{session_id}'.",
        )

    # Remove original staged file
    file_path = RESUME_STORAGE_DIR / resume.storage_name
    try:
        if file_path.exists():
            file_path.unlink()
    except OSError:
        pass

    # Remove any extracted text file
    extracted_path = (RESUME_STORAGE_DIR / session_id) / f"{resume_id}.txt"
    try:
        if extracted_path.exists():
            extracted_path.unlink()
    except OSError:
        pass

    # Remove vector chunks from Chroma collection if present
    delete_resume_from_index(session_id, resume_id)

    # Delete any existing evaluation for this resume while session is draft
    db.query(ResumeEvaluation).filter(
        ResumeEvaluation.screening_session_id == session_id,
        ResumeEvaluation.resume_id == resume_id,
    ).delete(synchronize_session=False)

    db.delete(resume)
    session.updated_at = get_utc_now()
    db.commit()
    return {
        "message": "Staged resume removed",
        "id": resume_id,
        "session_id": session_id,
    }


@app.post(
    "/api/screening-sessions/{session_id}/end",
    response_model=ScreeningSessionResponse,
)
def end_screening_session(
    session_id: str,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """
    End a screening session: clean up its staged temporary files and extracted text from disk,
    delete its resume metadata records, and set session status to 'ended'.
    """
    session = (
        db.query(ScreeningSession)
        .options(joinedload(ScreeningSession.job_description))
        .filter(ScreeningSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening session '{session_id}' not found.",
        )

    # Remove all temporary original resume files from disk
    resumes = (
        db.query(StagedResume)
        .filter(StagedResume.screening_session_id == session_id)
        .all()
    )
    for resume in resumes:
        file_path = RESUME_STORAGE_DIR / resume.storage_name
        try:
            if file_path.exists():
                file_path.unlink()
        except OSError:
            pass
        db.delete(resume)

    # Release ChromaDB file locks on Windows
    close_session_chroma(session_id)

    # Clean up session temporary directory containing extracted text files and chroma store
    session_storage_dir = RESUME_STORAGE_DIR / session_id
    remove_session_storage_dir(session_storage_dir)

    session.status = "ended"
    session.updated_at = get_utc_now()
    db.commit()
    db.refresh(session)
    return session


@app.post(
    "/api/screening-sessions/{session_id}/complete",
    response_model=ScreeningSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Complete a draft screening session and clean up temporary files",
)
def complete_screening_session(
    session_id: str,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """
    Explicitly complete a draft screening session:
    1. Requires an existing draft session (returns 404 if missing, 409 if not draft).
    2. Requires at least one persisted evaluation (returns 409 if no evaluations exist).
    3. Cleans up temporary original files, extracted text from disk, Chroma collections,
       and staged-resume metadata records using the established cleanup path.
    4. Sets session status to 'completed'.
    5. Retains the session and all validated ResumeEvaluation records.
    Accessible exclusively to Admins and Recruiters.
    """
    session = (
        db.query(ScreeningSession)
        .options(joinedload(ScreeningSession.job_description))
        .filter(ScreeningSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening session '{session_id}' not found.",
        )

    if session.status != SessionStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Screening session '{session_id}' is in '{session.status}' status. "
                "Only sessions in 'draft' status can be completed."
            ),
        )

    # Require at least one persisted evaluation
    eval_count = (
        db.query(ResumeEvaluation)
        .filter(ResumeEvaluation.screening_session_id == session_id)
        .count()
    )
    if eval_count == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Screening session '{session_id}' has no evaluated resumes. "
                "At least one evaluated resume is required before completing a session."
            ),
        )

    # Remove all temporary original resume files from disk
    resumes = (
        db.query(StagedResume)
        .filter(StagedResume.screening_session_id == session_id)
        .all()
    )
    for resume in resumes:
        file_path = RESUME_STORAGE_DIR / resume.storage_name
        try:
            if file_path.exists():
                file_path.unlink()
        except OSError:
            pass
        db.delete(resume)

    # Release ChromaDB file locks on Windows
    close_session_chroma(session_id)

    # Clean up session temporary directory containing extracted text files and chroma store
    session_storage_dir = RESUME_STORAGE_DIR / session_id
    remove_session_storage_dir(session_storage_dir)

    # Explicitly transition session status to 'completed'
    session.status = SessionStatus.COMPLETED.value
    session.updated_at = get_utc_now()
    db.commit()
    db.refresh(session)
    return session


@app.delete(
    "/api/screening-sessions/{session_id}",
    status_code=status.HTTP_200_OK,
    summary="Permanently delete a completed or ended screening session and its evaluations",
)
def delete_screening_session(
    session_id: str,
    current_user: User = Depends(require_admin_only),
    db: Session = Depends(get_db),
):
    """
    Permanently delete a completed or ended screening session:
    1. Requires Admin role; returns 401 unauthenticated, 403 for non-admins.
    2. Returns 404 if session is not found.
    3. Rejects draft sessions with 409 Conflict (they must use the end/cleanup workflow).
    4. Deletes the session and its ResumeEvaluation records in one database transaction.
    5. Does not delete or alter any other session or user data.
    """
    session = (
        db.query(ScreeningSession)
        .filter(ScreeningSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening session '{session_id}' not found.",
        )

    if session.status not in (SessionStatus.COMPLETED.value, SessionStatus.ENDED.value):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Screening session '{session_id}' is in '{session.status}' status. "
                "Only 'completed' or 'ended' sessions can be permanently deleted. "
                "Draft sessions must use the end/cleanup workflow first."
            ),
        )

    # In one database transaction, remove child evaluations and staged resumes, then session
    db.query(ResumeEvaluation).filter(
        ResumeEvaluation.screening_session_id == session_id
    ).delete(synchronize_session=False)

    db.query(StagedResume).filter(
        StagedResume.screening_session_id == session_id
    ).delete(synchronize_session=False)

    db.query(CandidateResult).filter(CandidateResult.session_id == session_id).delete(synchronize_session=False)
    db.query(SessionRun).filter(SessionRun.session_id == session_id).delete(synchronize_session=False)

    db.delete(session)
    db.commit()

    return {
        "message": f"Screening session '{session_id}' and its evaluation records were permanently deleted.",
        "id": session_id,
    }


@app.post(
    "/api/screening-sessions/{session_id}/index",
    response_model=list[StagedResumeResponse],
)
def index_screening_session_resumes(
    session_id: str,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """
    Index only staged resumes whose extraction_status is 'extracted' and whose
    temporary text file exists on disk into the session's ChromaDB collection.
    Skips empty, failed, and unsupported files without failing the session.
    Idempotent: replaces previous chunks for the resume.
    """
    session = (
        db.query(ScreeningSession)
        .filter(ScreeningSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening session '{session_id}' not found.",
        )

    if session.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Screening session '{session_id}' is in '{session.status}' status. "
                "Resumes can only be indexed for sessions in 'draft' status."
            ),
        )

    resumes = (
        db.query(StagedResume)
        .filter(StagedResume.screening_session_id == session_id)
        .order_by(StagedResume.created_at.asc())
        .all()
    )

    if not resumes:
        return []

    # Initialize chunker and embedding provider
    chunker = TextChunker()
    try:
        provider = get_embedding_provider()
    except EmbeddingModelSetupError as eme:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(eme),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize local embedding provider: {str(e)}",
        )

    session_storage_dir = RESUME_STORAGE_DIR / session_id

    for resume in resumes:
        if resume.extraction_status != "extracted":
            # Skip empty, failed, unsupported files without failing session
            resume.indexing_status = "skipped"
            resume.chunk_count = 0
            resume.indexing_error = (
                f"Skipped: extraction status is '{resume.extraction_status}'."
            )
            resume.updated_at = get_utc_now()
            continue

        extracted_file_path = session_storage_dir / f"{resume.id}.txt"
        if not extracted_file_path.exists():
            resume.indexing_status = "failed"
            resume.chunk_count = 0
            resume.indexing_error = "Extracted text file not found on disk."
            resume.updated_at = get_utc_now()
            continue

        try:
            raw_text = extracted_file_path.read_text(encoding="utf-8", errors="replace")
            chunks = chunker.chunk_text(raw_text)

            if not chunks:
                resume.indexing_status = "skipped"
                resume.chunk_count = 0
                resume.indexing_error = "No text chunks generated from document."
                resume.updated_at = get_utc_now()
                continue

            num_indexed = index_resume_chunks(
                session_id=session_id,
                resume_id=resume.id,
                source_filename=resume.original_filename,
                chunks=chunks,
                provider=provider,
            )

            resume.indexing_status = "indexed"
            resume.index_model = getattr(provider, "model_name", "nomic-embed-text")
            resume.chunk_count = num_indexed
            resume.indexing_error = None
            resume.updated_at = get_utc_now()

        except Exception as e:
            resume.indexing_status = "failed"
            resume.chunk_count = 0
            resume.indexing_error = f"Indexing failed: {str(e)}"
            resume.updated_at = get_utc_now()

    # Once the new index is successfully built for the session, clean up older model collections
    active_model_name = getattr(provider, "model_name", "nomic-embed-text")
    if any(r.indexing_status == "indexed" for r in resumes):
        cleanup_old_collections(session_id, active_model_name=active_model_name)

    session.updated_at = get_utc_now()
    db.commit()
    for resume in resumes:
        db.refresh(resume)

    return resumes


@app.post(
    "/api/screening-sessions/{session_id}/search",
    response_model=SemanticSearchResponse,
)
def search_screening_session_resumes(
    session_id: str,
    payload: SemanticSearchRequest,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """
    Search indexed resume chunks semantically within the specific screening session.
    Confined strictly to the requested session.
    """
    session = (
        db.query(ScreeningSession)
        .filter(ScreeningSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening session '{session_id}' not found.",
        )

    try:
        provider = get_embedding_provider()
    except EmbeddingModelSetupError as eme:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(eme),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize local embedding provider: {str(e)}",
        )

    try:
        results = search_session(
            session_id=session_id,
            query=payload.query,
            top_k=payload.top_k,
            provider=provider,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Semantic search failed: {str(e)}",
        )

    return SemanticSearchResponse(
        session_id=session_id,
        query=payload.query,
        results=[SearchResultItem(**r) for r in results],
    )


def derive_job_description_criteria(jd: JobDescription) -> list[tuple[str, str, str]]:
    """
    Derive retrieval criteria directly from the persisted Job Description record.
    Returns a list of tuples: (criterion_name, criterion_type, query_text).
    Never invents criteria beyond what is stated in the record.
    """
    criteria: list[tuple[str, str, str]] = []

    # 1. Stated skills
    skills = jd.skills if isinstance(jd.skills, list) else []
    for s in skills:
        clean_s = str(s).strip()
        if clean_s:
            criteria.append((clean_s, "skill", f"Proficiency and experience in {clean_s}"))

    # 2. Stated experience
    exp = (jd.experience or "").strip()
    if exp and exp.lower() not in ("not specified", "none", "n/a", ""):
        criteria.append((f"Experience: {exp}", "experience", f"Relevant background and experience: {exp}"))

    # 3. Stated role description / responsibilities
    desc = (jd.description or "").strip()
    if desc:
        criteria.append((f"Role: {jd.title}", "requirement", f"{jd.title}: {desc}"))
    elif not criteria:
        criteria.append((jd.title, "requirement", jd.title))

    return criteria


@app.post(
    "/api/screening-sessions/{session_id}/batch-evidence-retrieval",
    response_model=BatchEvidenceRetrievalResponse,
    summary="Batch local semantic evidence retrieval across all staged resumes",
)
def batch_retrieve_session_evidence(
    session_id: str,
    payload: BatchEvidenceRetrievalRequest | None = None,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """
    Role-protected batch local semantic evidence retrieval across all staged resumes
    for an active draft screening session.
    Retrieval-only: strictly uses the local embedding provider (nomic-embed-text) and
    the session's local Chroma vector collection.
    Never calls an LLM or any external/cloud service, and never generates evaluation records.
    Every staged resume is returned in the response with truthful retrieval status.
    """
    top_k = payload.top_k_per_criterion if payload else 3
    auto_process = payload.auto_extract_and_index if payload is not None else True

    # 1. Verify session exists and is in draft status
    session = (
        db.query(ScreeningSession)
        .options(joinedload(ScreeningSession.job_description))
        .filter(ScreeningSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening session '{session_id}' not found.",
        )

    if session.status != SessionStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Screening session '{session_id}' is in '{session.status}' status. "
                "Batch evidence retrieval can only be performed on sessions in 'draft' status."
            ),
        )

    jd = session.job_description
    if not jd:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job Description linked to session '{session_id}' not found.",
        )

    # 2. Get staged resumes
    resumes = (
        db.query(StagedResume)
        .filter(StagedResume.screening_session_id == session_id)
        .order_by(StagedResume.created_at.asc())
        .all()
    )

    if not resumes:
        jd_summary = BatchRetrievalJobDescriptionSummary(
            id=jd.id,
            title=jd.title,
            category=jd.category,
            experience=jd.experience,
            skills=jd.skills if isinstance(jd.skills, list) else [],
        )
        return BatchEvidenceRetrievalResponse(
            session_id=session_id,
            job_description=jd_summary,
            total_resumes=0,
            processed_resumes=0,
            resumes=[],
        )

    # 3. Optional auto extraction & indexing for any pending resumes
    session_storage_dir = RESUME_STORAGE_DIR / session_id
    session_storage_dir.mkdir(parents=True, exist_ok=True)

    if auto_process:
        # Check extraction
        pending_extraction = [r for r in resumes if r.extraction_status == "pending"]
        if pending_extraction:
            for resume in pending_extraction:
                file_path = RESUME_STORAGE_DIR / resume.storage_name
                ext_status, extracted_text, ext_err = extract_resume_text(
                    file_path=file_path,
                    file_type=resume.file_type,
                )
                extracted_file_path = session_storage_dir / f"{resume.id}.txt"
                if ext_status == "extracted":
                    extracted_file_path.write_text(extracted_text, encoding="utf-8")
                else:
                    if extracted_file_path.exists():
                        try:
                            extracted_file_path.unlink()
                        except OSError:
                            pass
                resume.extraction_status = ext_status
                resume.extraction_error = ext_err
                resume.updated_at = get_utc_now()
            session.updated_at = get_utc_now()
            db.commit()

        # Check indexing
        try:
            active_model = getattr(get_embedding_provider(), "model_name", "nomic-embed-text")
        except Exception:
            active_model = "nomic-embed-text"

        needs_indexing = [
            r for r in resumes
            if r.extraction_status == "extracted"
            and (r.indexing_status != "indexed" or r.index_model != active_model)
        ]
        if needs_indexing:
            chunker = TextChunker()
            try:
                provider = get_embedding_provider()
                for resume in needs_indexing:
                    extracted_file_path = session_storage_dir / f"{resume.id}.txt"
                    if not extracted_file_path.exists():
                        resume.indexing_status = "failed"
                        resume.chunk_count = 0
                        resume.indexing_error = "Extracted text file not found on disk."
                        resume.updated_at = get_utc_now()
                        continue
                    try:
                        raw_text = extracted_file_path.read_text(encoding="utf-8", errors="replace")
                        chunks = chunker.chunk_text(raw_text)
                        if not chunks:
                            resume.indexing_status = "skipped"
                            resume.chunk_count = 0
                            resume.indexing_error = "No text chunks generated from document."
                            resume.updated_at = get_utc_now()
                            continue
                        num_indexed = index_resume_chunks(
                            session_id=session_id,
                            resume_id=resume.id,
                            source_filename=resume.original_filename,
                            chunks=chunks,
                            provider=provider,
                        )
                        resume.indexing_status = "indexed"
                        resume.index_model = active_model
                        resume.chunk_count = num_indexed
                        resume.indexing_error = None
                        resume.updated_at = get_utc_now()
                    except Exception as e:
                        resume.indexing_status = "failed"
                        resume.chunk_count = 0
                        resume.indexing_error = f"Indexing failed: {str(e)}"
                        resume.updated_at = get_utc_now()

                cleanup_old_collections(session_id, active_model_name=active_model)
                session.updated_at = get_utc_now()
                db.commit()
            except Exception:
                pass

    # 4. Derive criteria queries from Job Description record
    criteria = derive_job_description_criteria(jd)

    # 5. Get local embedding provider and embed all criteria queries
    try:
        provider = get_embedding_provider()
    except EmbeddingModelSetupError as eme:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(eme),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize local embedding provider: {str(e)}",
        )

    criteria_queries = [c[2] for c in criteria]
    criteria_embeddings = provider.embed_documents(criteria_queries) if criteria_queries else []

    # 6. Retrieve evidence for each staged resume
    resume_items: list[ResumeBatchRetrievalItem] = []

    for resume in resumes:
        # Check extraction status
        if resume.extraction_status != "extracted":
            if resume.extraction_status == "unsupported":
                stat = "unsupported"
                reason = resume.extraction_error or f"Format '{resume.file_type}' is unsupported for local text extraction."
            elif resume.extraction_status == "failed":
                stat = "extraction_failed"
                reason = resume.extraction_error or "Text extraction failed."
            elif resume.extraction_status == "empty":
                stat = "empty_content"
                reason = resume.extraction_error or "Document contains no extractable text."
            else:
                stat = "unextracted"
                reason = "Resume text has not been extracted yet."

            resume_items.append(
                ResumeBatchRetrievalItem(
                    resume_id=resume.id,
                    source_filename=resume.original_filename,
                    file_type=resume.file_type,
                    file_size=resume.file_size,
                    extraction_status=resume.extraction_status,
                    indexing_status=resume.indexing_status,
                    status=stat,
                    status_reason=reason,
                    criteria_groups=[],
                    total_retrieved_chunks=0,
                )
            )
            continue

        # Check indexing status
        if resume.indexing_status != "indexed":
            if resume.indexing_status == "needs_reindex":
                stat = "needs_reindex"
                reason = resume.indexing_error or "Resume requires re-indexing with the active embedding model."
            elif resume.indexing_status == "skipped":
                stat = "skipped"
                reason = resume.indexing_error or "Resume indexing was skipped."
            elif resume.indexing_status == "failed":
                stat = "indexing_failed"
                reason = resume.indexing_error or "Resume indexing failed."
            else:
                stat = "unindexed"
                reason = "Resume has not been indexed into vector store."

            resume_items.append(
                ResumeBatchRetrievalItem(
                    resume_id=resume.id,
                    source_filename=resume.original_filename,
                    file_type=resume.file_type,
                    file_size=resume.file_size,
                    extraction_status=resume.extraction_status,
                    indexing_status=resume.indexing_status,
                    status=stat,
                    status_reason=reason,
                    criteria_groups=[],
                    total_retrieved_chunks=0,
                )
            )
            continue

        # If extracted and indexed, query Chroma vector store for this resume
        chunks_by_crit = batch_search_criteria_for_resume(
            session_id=session_id,
            resume_id=resume.id,
            query_embeddings=criteria_embeddings,
            top_k=top_k,
            provider=provider,
        )

        groups: list[CriterionEvidenceGroup] = []
        total_chunks_for_resume = 0

        for idx, (crit_name, crit_type, query_str) in enumerate(criteria):
            retrieved_chunks = chunks_by_crit[idx] if idx < len(chunks_by_crit) else []
            chunk_objs: list[RetrievedEvidenceChunk] = []

            for rc in retrieved_chunks:
                chunk_objs.append(
                    RetrievedEvidenceChunk(
                        criterion=crit_name,
                        criterion_type=crit_type,
                        query_text=query_str,
                        chunk_text=rc["chunk_text"],
                        chunk_index=rc["chunk_index"],
                        similarity_distance=rc["similarity_distance"],
                    )
                )

            total_chunks_for_resume += len(chunk_objs)
            groups.append(
                CriterionEvidenceGroup(
                    criterion=crit_name,
                    criterion_type=crit_type,
                    query_text=query_str,
                    chunks=chunk_objs,
                )
            )

        if total_chunks_for_resume > 0:
            stat = "evidence_retrieved"
            reason = None
        else:
            stat = "no_evidence_retrieved"
            reason = "No relevant text chunks retrieved for the criteria."

        resume_items.append(
            ResumeBatchRetrievalItem(
                resume_id=resume.id,
                source_filename=resume.original_filename,
                file_type=resume.file_type,
                file_size=resume.file_size,
                extraction_status=resume.extraction_status,
                indexing_status=resume.indexing_status,
                status=stat,
                status_reason=reason,
                criteria_groups=groups,
                total_retrieved_chunks=total_chunks_for_resume,
            )
        )

    # Return resumes in stable upload/creation order without derived scoring or ranking
    jd_summary = BatchRetrievalJobDescriptionSummary(
        id=jd.id,
        title=jd.title,
        category=jd.category,
        experience=jd.experience,
        skills=jd.skills if isinstance(jd.skills, list) else [],
    )

    return BatchEvidenceRetrievalResponse(
        session_id=session_id,
        job_description=jd_summary,
        total_resumes=len(resumes),
        processed_resumes=len([r for r in resume_items if r.status in ("evidence_retrieved", "no_evidence_retrieved")]),
        resumes=resume_items,
    )


@app.get(
    "/api/llm/status",
    response_model=LLMStatusResponse,
    summary="Get read-only LLM chat provider readiness status",
)
def get_llm_status(
    current_user: User = Depends(require_any_authenticated_user),
):
    """
    Read-only endpoint reporting Ollama chat provider readiness.
    Never exposes credentials, API keys, or secret environment settings.
    """
    llm_provider = get_llm_provider()
    is_enabled = getattr(llm_provider, "is_enabled", False)
    is_model_configured = getattr(llm_provider, "is_model_configured", False)
    cloud_usage_authorized = getattr(llm_provider, "cloud_usage_authorized", False)
    can_chat = getattr(llm_provider, "can_chat", False)
    model_name = getattr(llm_provider, "model_name", "") or None

    if not is_enabled:
        msg = (
            "Ollama LLM provider is disabled by default (OLLAMA_LLM_ENABLED=false). "
            "Set OLLAMA_LLM_ENABLED=true in environment settings to enable."
        )
    elif not is_model_configured:
        msg = (
            "Ollama provider is enabled, but no model name is configured. "
            "Set OLLAMA_MODEL_NAME in environment settings (e.g. gpt-oss:120b-cloud)."
        )
    elif not cloud_usage_authorized:
        msg = (
            "Ollama provider is enabled and configured, but cloud usage has not been authorized "
            "(OLLAMA_CLOUD_USAGE_AUTHORIZED=false). Enabling this setting authorizes requests to Ollama Cloud, "
            "which may incur token usage charges."
        )
    else:
        configured_name = model_name or "configured model"
        msg = (
            f"Ollama Cloud provider is ready with model '{configured_name}'. "
            "Cloud usage is authorized and may incur token charges ($0.15/M input tokens, $0.60/M output tokens)."
        )

    return LLMStatusResponse(
        is_enabled=is_enabled,
        is_model_configured=is_model_configured,
        cloud_usage_authorized=cloud_usage_authorized,
        can_chat=can_chat,
        message=msg,
        model_name=model_name,
    )


@app.get(
    "/api/system/status",
    response_model=SystemStatusResponse,
    summary="Get safe read-only system and runtime configuration status",
)
def get_system_status(
    current_user: User = Depends(require_any_authenticated_user),
):
    """
    Safe read-only status endpoint returning high-level system labels and configured model names.
    Strictly forbids exposing credentials, API keys, database URLs, or private filesystem paths.
    """
    db_engine = "SQLite" if DATABASE_URL.startswith("sqlite") else "PostgreSQL"
    embedding_provider_inst = get_embedding_provider()
    emb_model = getattr(embedding_provider_inst, "model_name", "nomic-embed-text")

    return SystemStatusResponse(
        backend_status="online",
        database_engine=db_engine,
        embedding_provider="ollama",
        embedding_model=emb_model,
        embedding_type="local",
        vector_store="ChromaDB",
        vector_store_isolation="per_session",
        resume_storage_lifecycle=(
            "Temporary resume files, extracted text, and Chroma vector embeddings are stored during "
            "active screening and automatically cleaned up and deleted upon session completion or termination. "
            "Validated candidate evaluations persist in the database until the session is explicitly deleted."
        ),
    )


@app.post(
    "/api/screening-sessions/{session_id}/ask",
    response_model=EvidenceChatResponse,
)
def ask_screening_session(
    session_id: str,
    payload: EvidenceChatRequest,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """
    Evidence-grounded chat endpoint for a screening session.
    Confirms the session exists and retrieves candidate evidence strictly
    from the session's local Chroma vector collection.
    Requires explicit per-request confirmation (confirm_cloud_transmission=True) before sending.
    If the LLM provider is disabled or unconfigured, returns HTTP 503 Service Unavailable.
    When explicitly enabled, provides the model only the question and retrieved evidence chunks,
    with strict guardrails: answer only from evidence, cite source filenames,
    do not infer protected characteristics, and do not make hiring decisions.
    """
    if not payload.confirm_cloud_transmission:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Evidence chat requires explicit confirmation before sending. "
                "You must confirm that your question and retrieved session evidence will be sent to "
                "Ollama Cloud and may incur usage charges."
            ),
        )

    session = (
        db.query(ScreeningSession)
        .filter(ScreeningSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening session '{session_id}' not found.",
        )

    # 1. Check LLM provider readiness before performing any vector search or LLM operation
    llm_provider = get_llm_provider()
    if not getattr(llm_provider, "can_chat", False):
        if not getattr(llm_provider, "is_enabled", False):
            detail_msg = (
                "LLM chat provider is disabled. "
                "Set OLLAMA_LLM_ENABLED=true in environment settings to enable."
            )
        elif not getattr(llm_provider, "is_model_configured", False):
            detail_msg = "Ollama model name is not configured. Cloud calls remain blocked."
        elif not getattr(llm_provider, "cloud_usage_authorized", False):
            detail_msg = (
                "Ollama Cloud usage has not been authorized (OLLAMA_CLOUD_USAGE_AUTHORIZED=false). "
                "Enabling this setting authorizes requests to Ollama Cloud, which may incur usage charges. "
                "Cloud calls remain blocked."
            )
        else:
            detail_msg = "LLM chat provider is not ready. Cloud calls remain blocked."

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail_msg,
        )

    # 2. Retrieve evidence strictly from session's local vector collection
    try:
        embedding_provider = get_embedding_provider()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize local embedding provider: {str(e)}",
        )

    try:
        search_results = search_session(
            session_id=session_id,
            query=payload.query,
            top_k=payload.top_k,
            provider=embedding_provider,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve resume evidence chunks: {str(e)}",
        )

    evidence_items = [SearchResultItem(**r) for r in search_results]

    # 3. Format evidence-grounded prompt with strict guardrails
    system_prompt = (
        "You are an evidence-grounded resume analysis assistant for a hiring team.\n"
        "STRICT CONSTRAINTS:\n"
        "1. Answer ONLY based on the provided resume evidence chunks below. Do not assume or invent facts.\n"
        "2. For each point or fact cited, explicitly identify the candidate's source filename.\n"
        "3. If the provided evidence is insufficient or does not contain the answer, explicitly state: "
        "'The provided resume evidence is insufficient to answer this question.'\n"
        "4. Do NOT infer protected personal characteristics (such as race, gender, age, religion, marital status, or nationality).\n"
        "5. Do NOT make hiring recommendations or final screening decisions."
    )

    evidence_text = "\n\n".join(
        f"--- Evidence Chunk {i + 1} ---\n"
        f"Source File: {r['source_filename']}\n"
        f"Chunk Index: {r['chunk_index']}\n"
        f"Text:\n{r['chunk_text']}"
        for i, r in enumerate(search_results)
    )

    user_prompt = (
        f"Provided Resume Evidence:\n"
        f"{evidence_text if evidence_text else 'No evidence chunks found in this session.'}\n\n"
        f"Question: {payload.query}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        answer = llm_provider.chat(messages)
    except LLMProviderDisabledError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM chat request failed: {str(e)}",
        )

    return EvidenceChatResponse(
        session_id=session_id,
        query=payload.query,
        answer=answer,
        evidence=evidence_items,
        model_name=getattr(llm_provider, "model_name", None),
    )


EVALUATION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "overall_score": {
            "type": "number",
            "description": "Numerical rating between 0.0 and 100.0",
        },
        "rubric": {
            "type": "array",
            "description": "Evaluation of each required job criterion",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {
                        "type": "string",
                        "description": "Specific Job Description requirement or skill name",
                    },
                    "criterion_type": {
                        "type": "string",
                        "enum": ["skill", "experience", "role_requirement"],
                    },
                    "score": {
                        "type": "number",
                        "description": "Numerical score from 0.0 to 5.0",
                    },
                    "max_score": {
                        "type": "number",
                        "description": "Maximum scale score (5.0)",
                    },
                    "evidence_status": {
                        "type": "string",
                        "enum": ["documented", "not_found_in_resume", "unknown"],
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Concise factual explanation of what evidence was or was not found in the resume text",
                    },
                    "evidence_quotes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of direct verbatim quote substrings from the resume text",
                    },
                },
                "required": [
                    "criterion",
                    "criterion_type",
                    "score",
                    "max_score",
                    "evidence_status",
                    "explanation",
                    "evidence_quotes",
                ],
            },
        },
        "missing_criteria": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Stated criteria not mentioned in the resume text",
        },
        "unverified_criteria": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Criteria with ambiguous or unclear documentation",
        },
        "evaluation_summary": {
            "type": "string",
            "description": "Objective summary of evidence coverage against job requirements",
        },
    },
    "required": [
        "overall_score",
        "rubric",
        "missing_criteria",
        "unverified_criteria",
        "evaluation_summary",
    ],
}


@app.post(
    "/api/screening-sessions/{session_id}/resumes/{resume_id}/evaluate",
    response_model=ResumeEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate one staged resume against the session's Job Description",
)
def evaluate_staged_resume(
    session_id: str,
    resume_id: str,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """
    Evidence-based evaluation endpoint for one staged resume against its session's saved Job Description.
    Verifies session and resume eligibility and text extraction availability on disk.
    Strictly checks llm_provider.can_chat BEFORE reading or sending any resume text.
    If disabled or unverified, returns HTTP 503 without reading the text file or calling any model.
    Evaluates against stated skills, experience, and role description only.
    Distinguishes 'not_found_in_resume' from 'unknown', does not treat missing text as proof
    of lack of skill, evaluates no protected characteristics/proxies, and makes no hiring decision.
    """
    # 1. Verify session exists and is eligible
    session = (
        db.query(ScreeningSession)
        .options(joinedload(ScreeningSession.job_description))
        .filter(ScreeningSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening session '{session_id}' not found.",
        )

    if session.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Screening session '{session_id}' is in '{session.status}' status. "
                "Only sessions in 'draft' status are eligible for evaluation."
            ),
        )

    job_description = session.job_description
    if not job_description:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Linked Job Description not found for session '{session_id}'.",
        )

    # 2. Verify resume exists and has successful extraction
    resume = (
        db.query(StagedResume)
        .filter(
            StagedResume.id == resume_id,
            StagedResume.screening_session_id == session_id,
        )
        .first()
    )
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Staged resume '{resume_id}' not found in screening session '{session_id}'.",
        )

    if resume.extraction_status != "extracted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Resume '{resume.original_filename}' cannot be evaluated because extraction status is '{resume.extraction_status}'. "
                "Only resumes with successfully extracted text can be evaluated."
            ),
        )

    extracted_path = (RESUME_STORAGE_DIR / session_id) / f"{resume.id}.txt"
    if not extracted_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extracted text file for resume '{resume.original_filename}' not found on disk.",
        )

    # 3. Check llm_provider.can_chat BEFORE reading or sending resume text!
    # If false, return HTTP 503 immediately without reading the text file from disk or making any model call.
    llm_provider = get_llm_provider()
    if not getattr(llm_provider, "can_chat", False):
        if not getattr(llm_provider, "is_enabled", False):
            detail_msg = (
                "LLM chat provider is disabled. "
                "Set OLLAMA_LLM_ENABLED=true in environment settings to enable."
            )
        elif not getattr(llm_provider, "is_model_configured", False):
            detail_msg = "Ollama model name is not configured. Cloud calls remain blocked."
        elif not getattr(llm_provider, "cloud_usage_authorized", False):
            detail_msg = (
                "Ollama Cloud usage has not been authorized (OLLAMA_CLOUD_USAGE_AUTHORIZED=false). "
                "Enabling this setting authorizes requests to Ollama Cloud, which may incur usage charges. "
                "Cloud calls remain blocked."
            )
        else:
            detail_msg = "LLM chat provider is not ready. Cloud calls remain blocked."

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail_msg,
        )

    # 4. Only after can_chat passes, read the resume text file
    try:
        resume_text = extracted_path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read extracted resume text: {str(e)}",
        )

    # 5. Build evaluation prompt grounded strictly in stated Job Description requirements
    skills_list = job_description.skills if isinstance(job_description.skills, list) else []
    skills_formatted = ", ".join(skills_list) if skills_list else "None specified"

    system_prompt = (
        "You are an evidence-based resume evaluator for hiring teams.\n\n"
        "EVALUATION INSTRUCTIONS & CONSTRAINTS:\n"
        "1. Evaluate ONLY against the stated skills, experience, and role requirements of the provided Job Description.\n"
        "2. Ground every score and explanation strictly in verbatim evidence found in the candidate's resume text.\n"
        "3. For each criterion, produce an assessment with:\n"
        "   - 'criterion': name of the specific JD requirement or skill.\n"
        "   - 'criterion_type': 'skill', 'experience', or 'role_requirement'.\n"
        "   - 'score': numerical rating from 0.0 to 5.0.\n"
        "   - 'max_score': 5.0.\n"
        "   - 'evidence_status': strictly one of 'documented', 'not_found_in_resume', or 'unknown'.\n"
        "   - 'explanation': concise factual explanation of what evidence was or was not found.\n"
        "   - 'evidence_quotes': list of direct verbatim quote strings from the resume.\n"
        "4. CRITICAL DISTINCTION: Distinguish 'not_found_in_resume' (the resume contains no mention of this skill/experience) "
        "from 'unknown' (the resume mentions related concepts but documentation is ambiguous/unclear). "
        "Do NOT treat missing text as proof that the candidate lacks the skill.\n"
        "5. FAIRNESS & SAFETY: Base your evaluation solely on job-related qualifications. "
        "Do NOT infer, speculate upon, or reference protected characteristics (such as race, gender, age, religion, "
        "disability, national origin, marital status) or geographical/demographic proxies.\n"
        "6. NO HIRING RECOMMENDATIONS: Do NOT make a hiring recommendation (e.g., 'hire', 'reject', 'advance', 'recommend'). "
        "Provide only objective evaluation of evidence against job criteria.\n"
        "7. Response MUST be valid JSON adhering to the specified schema."
    )

    user_prompt = (
        f"JOB DESCRIPTION:\n"
        f"Title: {job_description.title}\n"
        f"Role Description: {job_description.description}\n"
        f"Required Experience: {job_description.experience}\n"
        f"Required Skills: {skills_formatted}\n\n"
        f"CANDIDATE RESUME ({resume.original_filename}):\n"
        f"{resume_text}\n\n"
        f"Return ONLY valid JSON with this structure:\n"
        f"{{\n"
        f'  "overall_score": <number between 0 and 100>,\n'
        f'  "rubric": [\n'
        f'    {{\n'
        f'      "criterion": "<criterion name>",\n'
        f'      "criterion_type": "skill" | "experience" | "role_requirement",\n'
        f'      "score": <0.0 to 5.0>,\n'
        f'      "max_score": 5.0,\n'
        f'      "evidence_status": "documented" | "not_found_in_resume" | "unknown",\n'
        f'      "explanation": "<concise explanation>",\n'
        f'      "evidence_quotes": ["<direct quote>"]\n'
        f'    }}\n'
        f'  ],\n'
        f'  "missing_criteria": ["<criteria not mentioned in resume>"],\n'
        f'  "unverified_criteria": ["<criteria with ambiguous evidence>"],\n'
        f'  "evaluation_summary": "<objective summary of evidence coverage>"\n'
        f"}}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw_response = llm_provider.chat(
            messages,
            temperature=0.0,
            format=EVALUATION_JSON_SCHEMA,
            max_tokens=2048,
        )
    except LLMProviderDisabledError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation request failed: {str(e)}",
        )

    # 6. Parse structured response and validate model output
    try:
        cleaned = raw_response.strip()
        # Remove any reasoning/thinking blocks if emitted by reasoning models
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned).strip()
        if "```" in cleaned:
            code_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
            if code_match:
                cleaned = code_match.group(1).strip()
            else:
                lines = cleaned.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            parsed = json.loads(cleaned[start : end + 1])
        else:
            parsed = json.loads(cleaned)
    except Exception:
        logger.warning(
            "Evaluation failed: model output could not be parsed as valid JSON for resume_id=%s, session_id=%s",
            resume_id,
            session_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI model returned invalid or unparseable JSON output.",
        )

    if not isinstance(parsed, dict):
        logger.warning(
            "Evaluation failed: model output is not a JSON object for resume_id=%s, session_id=%s",
            resume_id,
            session_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI model output structure is invalid (expected JSON object).",
        )

    raw_rubric = parsed.get("rubric")
    if not isinstance(raw_rubric, list) or len(raw_rubric) == 0:
        logger.warning(
            "Evaluation failed: model output missing required rubric list for resume_id=%s, session_id=%s",
            resume_id,
            session_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI model output is incomplete (missing or empty rubric assessment).",
        )

    raw_summary = parsed.get("evaluation_summary")
    if not raw_summary or not isinstance(raw_summary, str) or not raw_summary.strip():
        logger.warning(
            "Evaluation failed: model output missing evaluation_summary for resume_id=%s, session_id=%s",
            resume_id,
            session_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI model output is incomplete (missing evaluation summary).",
        )

    rubric_items: list[RubricCriterionItem] = []
    for idx, item in enumerate(raw_rubric):
        if not isinstance(item, dict):
            logger.warning(
                "Evaluation failed: rubric item %d is not an object for resume_id=%s",
                idx,
                resume_id,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AI model rubric item {idx + 1} is invalid.",
            )

        # Filter evidence quotes: only retain quotes supported by the source resume text
        raw_quotes = item.get("evidence_quotes", [])
        if isinstance(raw_quotes, list):
            verified_quotes = [
                str(q).strip()
                for q in raw_quotes
                if isinstance(q, str) and verify_quote_against_source(q, resume_text)
            ]
        else:
            verified_quotes = []

        try:
            criterion_str = str(item.get("criterion", "")).strip()
            explanation_str = str(item.get("explanation", "")).strip()
            if not criterion_str:
                raise ValueError("Missing criterion name")
            if not explanation_str:
                raise ValueError("Missing explanation")

            rubric_item = RubricCriterionItem(
                criterion=criterion_str,
                criterion_type=str(item.get("criterion_type", "skill")).strip(),
                score=float(item.get("score")),
                max_score=float(item.get("max_score", 5.0)),
                evidence_status=str(item.get("evidence_status", "")).strip(),
                explanation=explanation_str,
                evidence_quotes=verified_quotes,
            )
            rubric_items.append(rubric_item)
        except (ValueError, TypeError, ValidationError) as ve:
            logger.warning(
                "Evaluation failed: rubric item %d failed schema validation for resume_id=%s: %s",
                idx,
                resume_id,
                str(ve),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AI model rubric item {idx + 1} contains invalid or out-of-bounds fields.",
            )

    raw_overall = parsed.get("overall_score")
    overall_score: float | None = None
    if raw_overall is not None:
        try:
            overall_score = float(raw_overall)
            if not math.isfinite(overall_score) or overall_score < 0.0 or overall_score > 100.0:
                raise ValueError("overall_score out of bounds [0.0, 100.0]")
        except (ValueError, TypeError):
            logger.warning(
                "Evaluation failed: overall_score is invalid or out of bounds for resume_id=%s",
                resume_id,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI model overall_score is invalid or outside allowed bounds (0 to 100).",
            )

    try:
        response_data = ResumeEvaluationResponse(
            session_id=session_id,
            resume_id=resume_id,
            original_filename=resume.original_filename,
            job_description_id=job_description.id,
            job_title=job_description.title,
            overall_score=overall_score,
            max_overall_score=100.0,
            rubric=rubric_items,
            missing_criteria=[
                str(c).strip()
                for c in parsed.get("missing_criteria", [])
                if isinstance(c, (str, int, float)) and str(c).strip()
            ],
            unverified_criteria=[
                str(c).strip()
                for c in parsed.get("unverified_criteria", [])
                if isinstance(c, (str, int, float)) and str(c).strip()
            ],
            evaluation_summary=raw_summary.strip(),
            model_name=getattr(llm_provider, "model_name", None),
        )
    except (ValueError, ValidationError) as ve:
        logger.warning(
            "Evaluation failed: response schema validation failed for resume_id=%s: %s",
            resume_id,
            str(ve),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Evaluation response failed schema validation.",
        )

    # 7. Persist validated evaluation record to database (replace existing if re-evaluated)
    existing_eval = (
        db.query(ResumeEvaluation)
        .filter(
            ResumeEvaluation.screening_session_id == session_id,
            ResumeEvaluation.resume_id == resume_id,
        )
        .first()
    )
    evaluated_time = get_utc_now()
    rubric_dicts = [item.model_dump() for item in response_data.rubric]

    if existing_eval:
        existing_eval.original_filename = response_data.original_filename
        existing_eval.job_description_id = response_data.job_description_id
        existing_eval.job_title = response_data.job_title
        existing_eval.model_name = response_data.model_name
        existing_eval.evaluated_at = evaluated_time
        existing_eval.overall_score = response_data.overall_score
        existing_eval.max_overall_score = response_data.max_overall_score
        existing_eval.rubric = rubric_dicts
        existing_eval.missing_criteria = response_data.missing_criteria
        existing_eval.unverified_criteria = response_data.unverified_criteria
        existing_eval.evaluation_summary = response_data.evaluation_summary
        existing_eval.disclaimer = response_data.disclaimer
        existing_eval.updated_at = evaluated_time
    else:
        new_eval = ResumeEvaluation(
            screening_session_id=session_id,
            resume_id=resume_id,
            original_filename=response_data.original_filename,
            job_description_id=response_data.job_description_id,
            job_title=response_data.job_title,
            model_name=response_data.model_name,
            evaluated_at=evaluated_time,
            overall_score=response_data.overall_score,
            max_overall_score=response_data.max_overall_score,
            rubric=rubric_dicts,
            missing_criteria=response_data.missing_criteria,
            unverified_criteria=response_data.unverified_criteria,
            evaluation_summary=response_data.evaluation_summary,
            disclaimer=response_data.disclaimer,
            created_at=evaluated_time,
            updated_at=evaluated_time,
        )
        db.add(new_eval)

    db.commit()
    response_data.evaluated_at = evaluated_time

    return response_data


@app.get(
    "/api/screening-sessions/{session_id}/evaluations",
    response_model=list[ResumeEvaluationResponse],
    summary="Get all persisted resume evaluations for a screening session",
)
def get_session_evaluations(
    session_id: str,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """
    Retrieve all persisted resume evaluation records for a screening session.
    Accessible exclusively to Admins and Recruiters for draft and ended sessions.
    Viewer requests are blocked with HTTP 403.
    """
    session = (
        db.query(ScreeningSession)
        .filter(ScreeningSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening session '{session_id}' not found.",
        )

    evaluations = (
        db.query(ResumeEvaluation)
        .filter(ResumeEvaluation.screening_session_id == session_id)
        .order_by(ResumeEvaluation.evaluated_at.asc())
        .all()
    )

    return evaluations


@app.get(
    "/api/candidates",
    response_model=list[CandidateEvaluationDirectoryItem],
    summary="List persisted resume evaluations directory for Admin and Recruiter",
)
def list_candidates_directory(
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """
    Returns directory of persisted resume evaluation records across screening sessions.
    Exclusively accessible to Admins and Recruiters.
    Viewer requests are blocked with HTTP 403 Forbidden; unauthenticated requests with HTTP 401.
    Returns only directory metadata: evaluation ID, resume ID, original filename, session ID,
    job description title, evaluated timestamp, overall score, and evaluation summary.
    Never includes raw resume text, file bytes, extracted text, prompts, or vector chunks.
    """
    evaluations = (
        db.query(ResumeEvaluation)
        .order_by(ResumeEvaluation.evaluated_at.desc())
        .all()
    )
    # Include results from the new screening pipeline alongside legacy rubric evaluations.
    merged = list(evaluations) + candidate_directory_items(db)
    return sorted(
        merged,
        key=lambda e: (e["evaluated_at"] if isinstance(e, dict) else e.evaluated_at),
        reverse=True,
    )


@app.get(
    "/api/evaluations/{evaluation_id}",
    response_model=ResumeEvaluationResponse,
    summary="Get single persisted resume evaluation by evaluation ID",
)
def get_evaluation_by_id(
    evaluation_id: str,
    current_user: User = Depends(require_admin_or_recruiter),
    db: Session = Depends(get_db),
):
    """
    Retrieve a single existing persisted evaluation record by evaluation ID.
    Exclusively accessible to Admins and Recruiters.
    Does not perform any evaluation or model call.
    """
    evaluation = (
        db.query(ResumeEvaluation)
        .filter(ResumeEvaluation.id == evaluation_id)
        .first()
    )
    if not evaluation:
        mapped = candidate_result_as_evaluation(db, evaluation_id)
        if mapped is not None:
            return mapped
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation '{evaluation_id}' not found.",
        )
    return evaluation





