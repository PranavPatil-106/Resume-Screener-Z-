import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, JSON, DateTime, Integer, ForeignKey, Float, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship, validates
from database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    RECRUITER = "recruiter"
    VIEWER = "viewer"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INVITED = "invited"
    DISABLED = "disabled"


class SessionStatus(str, enum.Enum):
    DRAFT = "draft"
    COMPLETED = "completed"
    ENDED = "ended"



def get_utc_now():
    return datetime.now(timezone.utc)



class JobDescription(Base):
    """
    Job Description model compatible with both SQLite and PostgreSQL.
    """
    __tablename__ = "job_descriptions"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    title = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False, default="General")
    description = Column(Text, nullable=False)
    skills = Column(JSON, nullable=False, default=list)
    experience = Column(String(100), nullable=False, default="Not specified")
    employment_type = Column(String(100), nullable=False, default="Full-time")
    is_archived = Column(Boolean, nullable=False, default=False, index=True)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=get_utc_now)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=get_utc_now,
        onupdate=get_utc_now,
    )

    screening_sessions = relationship(
        "ScreeningSession",
        back_populates="job_description",
        cascade="all, delete-orphan",
    )


class ScreeningSession(Base):
    """
    Screening Session metadata model linked to a Job Description.
    """
    __tablename__ = "screening_sessions"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    job_description_id = Column(
        String(36),
        ForeignKey("job_descriptions.id"),
        nullable=False,
        index=True,
    )
    status = Column(String(50), nullable=False, default="draft")
    created_at = Column(DateTime, nullable=False, default=get_utc_now)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=get_utc_now,
        onupdate=get_utc_now,
    )

    job_description = relationship(
        "JobDescription",
        back_populates="screening_sessions",
    )

    resumes = relationship(
        "StagedResume",
        back_populates="screening_session",
        cascade="all, delete-orphan",
    )

    evaluations = relationship(
        "ResumeEvaluation",
        back_populates="screening_session",
        cascade="all, delete-orphan",
    )

    @property
    def job_description_title(self) -> str:
        return self.job_description.title if self.job_description else ""


class StagedResume(Base):
    """
    Metadata for staged candidate resume files associated with a ScreeningSession.
    Actual files are stored in temporary local storage outside the database.
    """
    __tablename__ = "staged_resumes"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    screening_session_id = Column(
        String(36),
        ForeignKey("screening_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_size = Column(Integer, nullable=False)
    storage_name = Column(String(255), nullable=False)
    extraction_status = Column(String(50), nullable=False, default="pending")
    extraction_error = Column(Text, nullable=True)
    indexing_status = Column(String(50), nullable=False, default="pending")
    chunk_count = Column(Integer, nullable=False, default=0)
    indexing_error = Column(Text, nullable=True)
    index_model = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, default=get_utc_now)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=get_utc_now,
        onupdate=get_utc_now,
    )

    screening_session = relationship(
        "ScreeningSession",
        back_populates="resumes",
    )


class User(Base):
    """
    User model for role-based access control (RBAC).
    Compatible with both SQLite and PostgreSQL.
    """
    __tablename__ = "users"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    email = Column(String(255), unique=True, index=True, nullable=False)
    role = Column(String(50), nullable=False, default=UserRole.RECRUITER.value)
    status = Column(String(50), nullable=False, default=UserStatus.ACTIVE.value)
    password_hash = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=get_utc_now)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=get_utc_now,
        onupdate=get_utc_now,
    )

    @validates("email")
    def validate_and_normalize_email(self, key, value):
        if not value or not isinstance(value, str):
            raise ValueError("Email must be a non-empty string.")
        normalized = value.strip().lower()
        if not normalized or "@" not in normalized:
            raise ValueError("Invalid email format.")
        return normalized

    @validates("role")
    def validate_role(self, key, value):
        valid_roles = {r.value for r in UserRole}
        if value not in valid_roles:
            raise ValueError(f"Invalid user role: {value}. Must be one of {valid_roles}.")
        return value

    @validates("status")
    def validate_status(self, key, value):
        valid_statuses = {s.value for s in UserStatus}
        if value not in valid_statuses:
            raise ValueError(f"Invalid user status: {value}. Must be one of {valid_statuses}.")
        return value

    sessions = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    invitations = relationship(
        "UserInvitation",
        foreign_keys="[UserInvitation.user_id]",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    created_invitations = relationship(
        "UserInvitation",
        foreign_keys="[UserInvitation.created_by_id]",
        back_populates="created_by",
    )


class UserSession(Base):
    """
    Persisted authentication sessions.
    Stores only a SHA-256 hash of the opaque session token.
    Compatible with both SQLite and PostgreSQL.
    """
    __tablename__ = "user_sessions"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=get_utc_now)

    user = relationship(
        "User",
        back_populates="sessions",
    )

    @property
    def is_active(self) -> bool:
        """Returns True if the session has not expired and has not been revoked."""
        if self.revoked_at is not None:
            return False
        now = get_utc_now()
        if self.expires_at.tzinfo is None:
            return self.expires_at > now.replace(tzinfo=None)
        return self.expires_at > now


class UserInvitation(Base):
    """
    Persisted user invitations for email-free, secure user activation.
    Stores only a SHA-256 hash of the one-time invitation token.
    Compatible with both SQLite and PostgreSQL.
    """
    __tablename__ = "user_invitations"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    accepted_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_by_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=get_utc_now)

    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="invitations",
    )
    created_by = relationship(
        "User",
        foreign_keys=[created_by_id],
        back_populates="created_invitations",
    )

    @property
    def is_valid(self) -> bool:
        """Returns True if the invitation has not been accepted, revoked, or expired."""
        if self.accepted_at is not None or self.revoked_at is not None:
            return False
        now = get_utc_now()
        if self.expires_at.tzinfo is None:
            return self.expires_at > now.replace(tzinfo=None)
        return self.expires_at > now


class ResumeEvaluation(Base):
    """
    Persisted evidence-based evaluation results for one staged candidate resume against its session's Job Description.
    Linked to the retained ScreeningSession. Persists only validated rubric scores, source quotes, and criteria.
    Never stores full resume text, raw prompts, file bytes, or vector embeddings.
    """
    __tablename__ = "resume_evaluations"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    screening_session_id = Column(
        String(36),
        ForeignKey("screening_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resume_id = Column(String(36), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    job_description_id = Column(String(36), nullable=False)
    job_title = Column(String(255), nullable=False)
    model_name = Column(String(100), nullable=True)
    evaluated_at = Column(DateTime, nullable=False, default=get_utc_now)
    overall_score = Column(Float, nullable=True)
    max_overall_score = Column(Float, nullable=False, default=100.0)
    rubric = Column(JSON, nullable=False)
    missing_criteria = Column(JSON, nullable=False)
    unverified_criteria = Column(JSON, nullable=False)
    evaluation_summary = Column(Text, nullable=False)
    disclaimer = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=get_utc_now)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=get_utc_now,
        onupdate=get_utc_now,
    )

    __table_args__ = (
        UniqueConstraint(
            "screening_session_id",
            "resume_id",
            name="uq_resume_evaluations_session_resume",
        ),
    )

    screening_session = relationship(
        "ScreeningSession",
        back_populates="evaluations",
    )

    @property
    def session_id(self) -> str:
        return self.screening_session_id


class SessionRun(Base):
    """
    One row per screening session: background pipeline progress, extracted JD requirements,
    and the structured conversational state used by Chat with Results.
    """
    __tablename__ = "session_runs"

    session_id = Column(String(36), primary_key=True)
    created_by_email = Column(String(255), nullable=True)
    status = Column(String(30), nullable=False, default="idle")  # idle | running | completed | failed
    stage = Column(String(60), nullable=True)
    percent = Column(Float, nullable=False, default=0.0)
    total = Column(Integer, nullable=False, default=0)
    processed = Column(Integer, nullable=False, default=0)
    activity = Column(JSON, nullable=False, default=list)
    requirements = Column(JSON, nullable=False, default=list)
    chat_state = Column(JSON, nullable=False, default=dict)
    scoring_mode = Column(String(20), nullable=True)  # llm | heuristic
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=get_utc_now)
    updated_at = Column(DateTime, nullable=False, default=get_utc_now, onupdate=get_utc_now)


class CandidateResult(Base):
    """
    Scored candidate for a screening session. Stores the structured analysis only
    (no resume file, no full resume text), so it can outlive the temporary session data.
    """
    __tablename__ = "candidate_results"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    session_id = Column(String(36), nullable=False, index=True)
    resume_id = Column(String(36), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    candidate_name = Column(String(255), nullable=False, default="")
    email = Column(String(255), nullable=True)
    experience_years = Column(Float, nullable=True)
    skills = Column(JSON, nullable=False, default=list)
    match_percent = Column(Float, nullable=False, default=0.0)
    tier = Column(String(20), nullable=False, default="low")  # strong | good | partial | low
    requirement_results = Column(JSON, nullable=False, default=list)
    matched = Column(JSON, nullable=False, default=list)
    partial = Column(JSON, nullable=False, default=list)
    missing = Column(JSON, nullable=False, default=list)
    highlights = Column(JSON, nullable=False, default=list)
    projects = Column(JSON, nullable=False, default=list)
    experience = Column(JSON, nullable=False, default=list)
    assessment = Column(Text, nullable=False, default="")
    scoring_mode = Column(String(20), nullable=True)
    shortlisted = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False, default="scored")  # scored | failed
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=get_utc_now)
    updated_at = Column(DateTime, nullable=False, default=get_utc_now, onupdate=get_utc_now)

    __table_args__ = (
        UniqueConstraint("session_id", "resume_id", name="uq_candidate_results_session_resume"),
    )





