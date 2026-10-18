import math
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class JobDescriptionBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Role title")
    category: str = Field(default="General", max_length=100, description="Department or job category")
    description: str = Field(..., min_length=1, description="Full job description text")
    skills: list[str] = Field(default_factory=list, description="Required candidate skills / tags")
    tags: list[str] | None = Field(default=None, description="Optional alias for skills")
    experience: str = Field(default="Not specified", max_length=100, description="Years of experience required")
    employment_type: str = Field(default="Full-time", max_length=100, description="Employment type (e.g. Full-time, Contract)")

    @model_validator(mode="after")
    def sync_skills_and_tags(self):
        # Allow either `tags` or `skills` to populate the list
        if self.tags is not None and not self.skills:
            self.skills = self.tags
        elif self.skills and self.tags is None:
            self.tags = self.skills
        return self


class JobDescriptionCreate(JobDescriptionBase):
    pass


class JobDescriptionUpdate(JobDescriptionBase):
    pass


class JobDescriptionResponse(BaseModel):
    id: str
    title: str
    category: str
    description: str
    skills: list[str]
    tags: list[str]
    experience: str
    employment_type: str
    is_archived: bool = False
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def populate_tags_from_skills(cls, data):
        # Support ORM models where only `skills` attribute exists
        if hasattr(data, "skills") and not hasattr(data, "tags"):
            skills_val = getattr(data, "skills") or []
            return {
                "id": getattr(data, "id"),
                "title": getattr(data, "title"),
                "category": getattr(data, "category"),
                "description": getattr(data, "description"),
                "skills": skills_val,
                "tags": skills_val,
                "experience": getattr(data, "experience"),
                "employment_type": getattr(data, "employment_type"),
                "is_archived": getattr(data, "is_archived", False),
                "archived_at": getattr(data, "archived_at", None),
                "created_at": getattr(data, "created_at"),
                "updated_at": getattr(data, "updated_at"),
            }
        elif isinstance(data, dict):
            skills_val = data.get("skills") or data.get("tags") or []
            data["skills"] = skills_val
            data["tags"] = skills_val
            if "is_archived" not in data:
                data["is_archived"] = False
            if "archived_at" not in data:
                data["archived_at"] = None
        return data


SessionStatusType = Literal["draft", "completed", "ended"]


class ScreeningSessionCreate(BaseModel):
    job_description_id: str = Field(..., description="ID of the associated Job Description")


class ScreeningSessionResponse(BaseModel):
    id: str
    job_description_id: str
    job_description_title: str
    status: SessionStatusType
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def extract_title(cls, data):
        if hasattr(data, "job_description") and getattr(data, "job_description"):
            jd = getattr(data, "job_description")
            return {
                "id": getattr(data, "id"),
                "job_description_id": getattr(data, "job_description_id"),
                "job_description_title": getattr(jd, "title", ""),
                "status": getattr(data, "status"),
                "created_at": getattr(data, "created_at"),
                "updated_at": getattr(data, "updated_at"),
            }
        elif isinstance(data, dict):
            if "job_description_title" not in data and "job_description" in data:
                jd = data["job_description"]
                data["job_description_title"] = jd.get("title", "") if isinstance(jd, dict) else getattr(jd, "title", "")
        return data


class StagedResumeResponse(BaseModel):
    id: str
    screening_session_id: str
    original_filename: str
    file_type: str
    file_size: int
    extraction_status: str = "pending"
    extraction_error: str | None = None
    indexing_status: str = "pending"
    chunk_count: int = 0
    indexing_error: str | None = None
    index_model: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DraftScreeningSessionResponse(BaseModel):
    id: str
    job_description_id: str
    job_description_title: str
    status: SessionStatusType
    created_at: datetime
    updated_at: datetime
    job_description: JobDescriptionResponse
    resumes: list[StagedResumeResponse] = Field(default_factory=list)
    evaluations: list["ResumeEvaluationResponse"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def populate_title(cls, data):
        if hasattr(data, "job_description") and getattr(data, "job_description"):
            jd = getattr(data, "job_description")
            if hasattr(data, "job_description_title") and not getattr(data, "job_description_title"):
                try:
                    setattr(data, "job_description_title", getattr(jd, "title", ""))
                except Exception:
                    pass
        elif isinstance(data, dict):
            if "job_description_title" not in data and "job_description" in data:
                jd = data["job_description"]
                data["job_description_title"] = jd.get("title", "") if isinstance(jd, dict) else getattr(jd, "title", "")
        return data


class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="Semantic search query")
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum number of top chunks to return (1-50)")


class SearchResultItem(BaseModel):
    chunk_text: str
    source_filename: str
    resume_id: str
    chunk_index: int
    similarity_distance: float


class SemanticSearchResponse(BaseModel):
    session_id: str
    query: str
    results: list[SearchResultItem]


class EvidenceChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="User question about candidate evidence")
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum number of evidence chunks to retrieve as context (1-50)")
    confirm_cloud_transmission: bool = Field(
        ...,
        description="Explicit confirmation that query and retrieved session evidence will be sent to Ollama Cloud and may incur usage charges",
    )


class EvidenceChatResponse(BaseModel):
    session_id: str
    query: str
    answer: str
    evidence: list[SearchResultItem]
    model_name: str | None = None


class LLMStatusResponse(BaseModel):
    is_enabled: bool = Field(..., description="Whether the LLM provider is explicitly enabled")
    is_model_configured: bool = Field(..., description="Whether a valid model name is configured")
    cloud_usage_authorized: bool = Field(..., description="Whether cloud usage has been explicitly authorized (may incur token charges)")
    can_chat: bool = Field(..., description="Whether all conditions are met to make chat calls")
    message: str = Field(..., description="Safe user-facing status message")
    model_name: str | None = Field(default=None, description="Configured Ollama Cloud model identifier (non-secret)")


class SystemStatusResponse(BaseModel):
    backend_status: str = Field(default="online", description="High-level backend health indicator")
    database_engine: str = Field(..., description="Active database engine ('SQLite' or 'PostgreSQL')")
    embedding_provider: str = Field(..., description="Active embedding provider name")
    embedding_model: str = Field(..., description="Configured embedding model identifier")
    embedding_type: str = Field(default="local", description="Type of embedding: 'local' (runs on-device)")
    vector_store: str = Field(default="ChromaDB", description="Vector database engine")
    vector_store_isolation: str = Field(default="per_session", description="Vector collection isolation mode")
    resume_storage_lifecycle: str = Field(..., description="Explanation of resume storage and retention lifecycle")


class RubricCriterionItem(BaseModel):
    criterion: str = Field(..., min_length=1, description="Job Description requirement or skill evaluated")
    criterion_type: str = Field(..., description="Type of criterion (e.g. 'skill', 'experience', 'role_requirement')")
    score: float = Field(..., description="Rubric score for this criterion (0.0 to 5.0)")
    max_score: float = Field(default=5.0, description="Maximum possible score for this criterion")
    evidence_status: str = Field(
        ...,
        description="Assessment status: 'documented', 'not_found_in_resume', or 'unknown'",
    )
    explanation: str = Field(..., description="Concise explanation grounded strictly in resume text")
    evidence_quotes: list[str] = Field(
        default_factory=list,
        description="Direct quotes from the resume supporting this criterion",
    )

    @model_validator(mode="after")
    def validate_scores_and_status(self):
        if not math.isfinite(self.score):
            raise ValueError("Criterion score must be a finite number.")
        if not math.isfinite(self.max_score) or self.max_score <= 0:
            raise ValueError("Criterion max_score must be a finite positive number.")
        if self.score < 0.0 or self.score > self.max_score:
            raise ValueError(f"Criterion score {self.score} is outside declared bounds [0.0, {self.max_score}].")
        valid_statuses = {"documented", "not_found_in_resume", "unknown"}
        if self.evidence_status not in valid_statuses:
            raise ValueError(f"Invalid evidence_status '{self.evidence_status}'. Must be one of {valid_statuses}.")
        return self


class ResumeEvaluationResponse(BaseModel):
    session_id: str
    resume_id: str
    original_filename: str
    job_description_id: str
    job_title: str
    overall_score: float | None = None
    max_overall_score: float = 100.0
    rubric: list[RubricCriterionItem]
    missing_criteria: list[str] = Field(
        default_factory=list,
        description="Criteria not documented in the resume text (absence of text is not proof of lack of skill)",
    )
    unverified_criteria: list[str] = Field(
        default_factory=list,
        description="Criteria where documentation is ambiguous or unknown",
    )
    evaluation_summary: str
    disclaimer: str = Field(
        default=(
            "Evaluation is grounded strictly on job-related resume text against stated JD requirements. "
            "Absence of text is not proof of lack of skill. No protected characteristics or proxies were evaluated. "
            "No automated hiring decision or recommendation is made."
        )
    )
    model_name: str | None = None
    evaluated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def populate_session_id(cls, data):
        if hasattr(data, "screening_session_id") and not hasattr(data, "session_id"):
            try:
                setattr(data, "session_id", getattr(data, "screening_session_id"))
            except Exception:
                pass
        elif isinstance(data, dict):
            if "session_id" not in data and "screening_session_id" in data:
                data["session_id"] = data["screening_session_id"]
        return data

    @model_validator(mode="after")
    def validate_overall_score_and_rubric(self):
        if not math.isfinite(self.max_overall_score) or self.max_overall_score <= 0:
            raise ValueError("max_overall_score must be a finite positive number.")
        if self.overall_score is not None:
            if not math.isfinite(self.overall_score):
                raise ValueError("overall_score must be a finite number.")
            if self.overall_score < 0.0 or self.overall_score > self.max_overall_score:
                raise ValueError(
                    f"overall_score {self.overall_score} is outside declared bounds [0.0, {self.max_overall_score}]."
                )
        if not self.rubric:
            raise ValueError("Evaluation rubric must contain at least one criterion item.")
        return self


class CandidateEvaluationDirectoryItem(BaseModel):
    id: str = Field(..., description="Evaluation ID")
    resume_id: str = Field(..., description="Staged resume ID")
    original_filename: str = Field(..., description="Source resume filename")
    session_id: str = Field(..., description="Screening session ID")
    job_description_title: str = Field(..., description="Job Description title")
    evaluated_at: datetime = Field(..., description="Timestamp of evaluation")
    overall_score: float | None = Field(default=None, description="Persisted rubric overall score")
    max_overall_score: float = Field(default=100.0, description="Max overall score")
    evaluation_summary: str = Field(..., description="Persisted evaluation summary")

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def populate_fields(cls, data):
        # Map screening_session_id -> session_id if needed
        if hasattr(data, "screening_session_id") and not hasattr(data, "session_id"):
            try:
                setattr(data, "session_id", getattr(data, "screening_session_id"))
            except Exception:
                pass
        elif isinstance(data, dict):
            if "session_id" not in data and "screening_session_id" in data:
                data["session_id"] = data["screening_session_id"]
        # Map job_title -> job_description_title if needed
        if hasattr(data, "job_title") and not hasattr(data, "job_description_title"):
            try:
                setattr(data, "job_description_title", getattr(data, "job_title"))
            except Exception:
                pass
        elif isinstance(data, dict):
            if "job_description_title" not in data and "job_title" in data:
                data["job_description_title"] = data["job_title"]
        return data


DraftScreeningSessionResponse.model_rebuild()


# User & RBAC schemas (Password hash is strictly omitted)
UserRoleType = Literal["admin", "recruiter", "viewer"]
UserStatusType = Literal["active", "invited", "disabled"]
UserStatusUpdateType = Literal["active", "disabled"]


class UserBase(BaseModel):
    email: str = Field(..., max_length=255, description="Normalized user email address")
    role: UserRoleType = Field(default="recruiter", description="Assigned role: admin, recruiter, or viewer")
    status: UserStatusType = Field(default="active", description="Account status: active, invited, or disabled")

    @model_validator(mode="before")
    @classmethod
    def normalize_email(cls, data):
        if isinstance(data, dict) and "email" in data and isinstance(data["email"], str):
            data["email"] = data["email"].strip().lower()
        return data


class UserResponse(BaseModel):
    id: str = Field(..., description="Unique UUID identifier for the user")
    email: str = Field(..., description="Normalized user email address")
    role: UserRoleType = Field(..., description="Assigned user role (admin, recruiter, or viewer)")
    status: UserStatusType = Field(..., description="User account status (active, invited, or disabled)")
    created_at: datetime = Field(..., description="User creation timestamp (UTC)")
    updated_at: datetime = Field(..., description="User last updated timestamp (UTC)")

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: str = Field(..., max_length=255, description="User email address")
    password: str = Field(..., min_length=1, description="User password")

    @model_validator(mode="before")
    @classmethod
    def normalize_email(cls, data):
        if isinstance(data, dict) and "email" in data and isinstance(data["email"], str):
            data["email"] = data["email"].strip().lower()
        return data


class LogoutResponse(BaseModel):
    message: str = "Logged out successfully"


class InviteUserRequest(BaseModel):
    email: str = Field(..., max_length=255, description="Normalized email of user to invite")
    role: UserRoleType = Field(..., description="Role to assign to invited user: admin, recruiter, or viewer")

    @model_validator(mode="before")
    @classmethod
    def normalize_email(cls, data):
        if isinstance(data, dict) and "email" in data and isinstance(data["email"], str):
            data["email"] = data["email"].strip().lower()
        return data


class InviteUserResponse(BaseModel):
    user: UserResponse
    invitation_token: str = Field(
        ...,
        description="One-time plaintext invitation token. Must be shared manually over a secure channel; cannot be retrieved again.",
    )
    expires_at: datetime
    message: str = (
        "User invitation created. The invitation token must be shared manually with the user "
        "through a secure channel because email delivery is not configured."
    )


class AcceptInvitationRequest(BaseModel):
    token: str = Field(..., min_length=1, description="One-time plaintext invitation token")
    password: str = Field(..., min_length=8, description="New account password (minimum 8 characters)")


class AcceptInvitationResponse(BaseModel):
    message: str = "Invitation accepted successfully. Account is now active."
    user: UserResponse


class UpdateUserRoleRequest(BaseModel):
    role: UserRoleType = Field(..., description="Target role: admin, recruiter, or viewer")


class UpdateUserStatusRequest(BaseModel):
    status: UserStatusUpdateType = Field(..., description="Target status: active or disabled")


class RetrievedEvidenceChunk(BaseModel):
    criterion: str = Field(..., description="Name of the Job Description criterion")
    criterion_type: str = Field(..., description="Type of criterion: skill, experience, or requirement")
    query_text: str = Field(..., description="Search query derived directly from the criterion")
    chunk_text: str = Field(..., description="Verbatim chunk text retrieved from candidate resume")
    chunk_index: int = Field(..., description="0-based index of the chunk in the resume")
    similarity_distance: float = Field(
        ...,
        description="Cosine vector distance for retrieval only (lower indicates closer distance in vector space)",
    )


class CriterionEvidenceGroup(BaseModel):
    criterion: str
    criterion_type: str
    query_text: str
    chunks: list[RetrievedEvidenceChunk] = []


class ResumeBatchRetrievalItem(BaseModel):
    resume_id: str
    source_filename: str
    file_type: str
    file_size: int
    extraction_status: str
    indexing_status: str
    status: str = Field(
        ...,
        description=(
            "Retrieval status: 'evidence_retrieved', 'no_evidence_retrieved', 'unextracted', "
            "'unindexed', 'unsupported', 'extraction_failed', 'empty_content', or 'skipped'"
        ),
    )
    status_reason: Optional[str] = None
    criteria_groups: list[CriterionEvidenceGroup] = []
    total_retrieved_chunks: int = 0


class BatchRetrievalJobDescriptionSummary(BaseModel):
    id: str
    title: str
    category: str
    experience: str
    skills: list[str] = []


class BatchEvidenceRetrievalRequest(BaseModel):
    top_k_per_criterion: int = Field(default=3, ge=1, le=10, description="Max chunks to retrieve per criterion")
    auto_extract_and_index: bool = Field(
        default=True,
        description="Whether to automatically extract and index pending resumes before retrieval",
    )


class BatchEvidenceRetrievalResponse(BaseModel):
    session_id: str
    job_description: BatchRetrievalJobDescriptionSummary
    total_resumes: int
    processed_resumes: int
    resumes: list[ResumeBatchRetrievalItem]


