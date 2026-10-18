# AI Resume Screener Backend

FastAPI application with SQLAlchemy and Alembic, managed with `uv`.

## Architecture & Configuration

- **Database**: Default SQLite file at `backend/data/app.db` (ignored by Git).
- **Environment Variable**: `DATABASE_URL` can be specified to switch to PostgreSQL (e.g. `postgresql+psycopg2://user:password@host:5432/resumescreener`).
- **Temporary Resume Storage**: Files staged to `RESUME_STORAGE_DIR` (defaults to `backend/data/staged_resumes`, ignored by Git).
- **Size Limits & Types**:
  - `MAX_FILE_SIZE_BYTES`: Max per-file upload size (default `15728640` bytes / 15 MB).
  - `MAX_BATCH_SIZE_BYTES`: Max total-batch upload size (default `314572800` bytes / 300 MB, comfortably supporting batches of 50+ resumes).
  - `MAX_ZIP_MEMBERS`: Max members in a staged ZIP archive (default `200`).
  - `MAX_ZIP_UNCOMPRESSED_SIZE_BYTES`: Max total uncompressed size for a ZIP (default `209715200` bytes / 200 MB).
  - `MAX_ZIP_COMPRESSION_RATIO`: Max compression ratio to prevent zip bombs (default `100.0`).
  - Supported file extensions: `.pdf`, `.doc`, `.docx`, `.zip`.
- **Text Extraction**:
  - Supports `.pdf`, `.docx`, and `.zip` archives containing PDF/DOCX members.
  - ZIP archives are inspected in-memory with strict path validation and zero filesystem extraction.
  - Member texts are combined into temporary `{resume_id}.txt` files separated by member headers.
  - `.doc` remains unsupported for extraction while preserving staged originals.
- **Local Vector Embeddings & Search**:
  - Local embedding provider powered by local Ollama (`http://127.0.0.1:11434/api/embed`) using standard library HTTP requests (`backend/embedding_provider.py`).
  - Default model: `nomic-embed-text` (768 dimensions).
  - The local embedding model is downloaded once to your local Ollama library (`ollama pull nomic-embed-text`) and runs locally. Resume text stays on this device for embedding generation and is never transmitted to Ollama Cloud or any external API.
  - Session-scoped local Chroma collections manage vector indexing and similarity search with model-versioned collections.
- **ORM & Migrations**: SQLAlchemy 2.x and Alembic.

## Database Migrations

Apply current migrations:
```bash
uv run alembic upgrade head
```

Create a new migration after editing `models.py`:
```bash
uv run alembic revision --autogenerate -m "describe_changes"
```

## Initial Administrator Account Creation

To initialize the first administrator account, run the interactive CLI command:

```bash
cd backend
uv run python create_admin.py
```

**Security & Safeguards**:
- Prompts interactively for the administrator's email and password (with hidden password entry and confirmation).
- Passwords are never accepted as command-line arguments, environment variables, or printed/logged.
- Hashes passwords using Argon2id (`argon2-cffi`).
- **One-Time Guard**: The command strictly refuses to execute if any user account already exists in the database.

## Running the API

Start the development server:
```bash
uv run uvicorn main:app --reload --port 8000
```

## Endpoints

- `GET /health` - Health check verification
- `POST /api/auth/login` - Authenticate via email/password, issue session, set HTTP-only cookie, and return `UserResponse`
- `POST /api/auth/logout` - Revoke active session in the database and clear the authentication cookie
- `GET /api/auth/me` - Return currently authenticated user profile (`UserResponse`)
- `GET /api/job-descriptions` - List all persisted job descriptions
- `POST /api/job-descriptions` - Create a new job description
- `GET /api/screening-sessions` - List screening sessions with associated Job Description title
- `POST /api/screening-sessions` - Create a new draft screening session
- `POST /api/screening-sessions/{session_id}/resumes` - Stage multiple resumes (`.pdf`, `.doc`, `.docx`, `.zip`) for a draft session
- `GET /api/screening-sessions/{session_id}/resumes` - List staged resume metadata for a session
- `POST /api/screening-sessions/{session_id}/extract-text` - Extract text from staged PDF and DOCX files into session temporary storage directory
- `DELETE /api/screening-sessions/{session_id}/resumes/{resume_id}` - Remove a staged resume by ID and delete its temporary files
- `POST /api/screening-sessions/{session_id}/end` - End session, clean up temporary disk files, extracted text, and resume metadata, set status to `ended`
- `GET /api/llm/status` - Read-only provider readiness status (`can_chat`, `is_enabled`, `is_model_configured`, `cloud_usage_authorized`)
- `POST /api/screening-sessions/{session_id}/ask` - Evidence-grounded Q&A answered strictly from session vector search chunks (requires explicit `confirm_cloud_transmission: true`)
- `POST /api/screening-sessions/{session_id}/resumes/{resume_id}/evaluate` - Guarded single-resume rubric evaluation against Job Description (manual, single-candidate)
- `GET /docs` - Interactive OpenAPI Swagger documentation

## Authentication & Session Architecture

The backend implements local authentication with hardened session persistence:

### 1. Token Generation & Storage
- Opaque, cryptographically secure 32-byte tokens are generated via `secrets.token_urlsafe(32)`.
- **Database Storage**: Raw tokens are **never** stored in the database. Only the SHA-256 hash (`token_hash`) is persisted in the `user_sessions` table.
- Sessions include `expires_at` (default 7 days) and `revoked_at` timestamps. Expired or revoked sessions fail authentication immediately.

### 2. Cookie Management & Security Settings
- The raw token is delivered exclusively via an `HttpOnly`, `SameSite=Lax` browser cookie (`auth_session`).
- **`AUTH_COOKIE_SECURE`**:
  - Default: `False` for local HTTP development.
  - **Production Requirement**: In production, `AUTH_COOKIE_SECURE` must be set to `True` (e.g. `AUTH_COOKIE_SECURE=true`) to enforce that the cookie is transmitted strictly over HTTPS.
- **`SESSION_MAX_AGE_SECONDS`**: Configurable session lifespan (defaults to `604800` seconds / 7 days).
- **`CORS_ORIGINS`**: Comma-separated list of exact frontend origins (defaults to `http://localhost:5173,http://127.0.0.1:5173`). Credentials (`allow_credentials=True`) are supported only for exact origins; wildcards are strictly disallowed with credentials.

### 3. Role-Based Access Control (RBAC) Policy
- **Public Routes**:
  - `GET /health` (service health check)
  - `POST /api/auth/login` (authentication entrypoint)
  - `POST /api/auth/logout` (session revocation and cookie cleanup)
- **Authenticated Routes (Admin, Recruiter, Viewer)**:
  - `GET /api/auth/me` (current user profile)
  - `GET /api/job-descriptions` (list job descriptions)
  - `GET /api/screening-sessions` (list screening session metadata; viewers receive completed sessions only)
- **Privileged Workflow Routes (Admin & Recruiter Only)**:
  - `POST /api/job-descriptions` (create job descriptions)
  - `POST /api/screening-sessions` (create draft screening sessions)
  - Resume staging, extraction, and management (`/api/screening-sessions/{session_id}/resumes`, `/api/screening-sessions/{session_id}/extract-text`, DELETE resume)
  - Indexing, search, and cleanup (`/api/screening-sessions/{session_id}/index`, `/api/screening-sessions/{session_id}/search`, `/api/screening-sessions/{session_id}/end`)
  - AI chat, status, and evaluation (`/api/llm/status`, `/api/screening-sessions/{session_id}/ask`, `/api/screening-sessions/{session_id}/resumes/{resume_id}/evaluate`)
- **Error Codes**: Returns `401 Unauthorized` for unauthenticated requests and `403 Forbidden` for authenticated users lacking required role permissions. Authorization responses never leak resource or user existence.
- **Single-Workspace Model**: Note that this implements local role-based access control within the local workspace; it does not claim multi-tenant isolation.

## Guarded Ollama Cloud Evaluation & Privacy Architecture

The backend implements a **local-first, fail-closed privacy architecture**. All generative AI cloud features are disabled by default.

### 1. Disabled by Default: Required Readiness Gate (`can_chat`)
Before any chat or evaluation request can be processed, all three conditions must be satisfied:
1. `OLLAMA_LLM_ENABLED=true` (and `LLM_PROVIDER=ollama`).
2. `OLLAMA_MODEL_NAME` must be non-empty (e.g., `gpt-oss:120b-cloud`).
3. `OLLAMA_CLOUD_USAGE_AUTHORIZED=true` (defaults to `false`).

If any condition is not met, endpoints return `HTTP 503 Service Unavailable` immediately before reading resume text or issuing any model requests.

### 2. Cloud Usage Authorization & Billing Terms
Setting `OLLAMA_CLOUD_USAGE_AUTHORIZED=true` is an explicit opt-in authorizing token-based Ollama Cloud usage:
- Ollama's current listed rate for `gpt-oss:120b-cloud` is $0.15 per million input tokens and $0.60 per million output tokens.
- Do not describe this setting as zero-cost verification.
- The system does not assume that the user's account has a hard spending limit or that the model is covered by a free allowance.

### 3. Evaluation Flow & Data Transmission Scope
When `POST /api/screening-sessions/{session_id}/resumes/{resume_id}/evaluate` is invoked:
- It runs **strictly manually and per-resume**; resumes are never evaluated in batches or automatically.
- Requires both backend readiness (`can_chat: true`) and explicit unchecked per-resume confirmation in the UI.
- The request transmits only the candidate's extracted plain text and the linked Job Description criteria to Ollama Cloud.
- The endpoint evaluates strictly against stated skills, experience, and role criteria. It does not infer protected personal characteristics and makes no automated hiring decisions.
- Validated evaluation results, rubric assessments, scores, explanations, verified evidence quotes, summaries, and related metadata persist in the local `resume_evaluations` table. Original resume files, extracted text, and Chroma vector data remain temporary and are removed when a session is completed or ended. Permanently deleting an eligible completed or ended session removes its associated evaluation records.

### 4. Structured Output Validation & Quote Verification
Before the evaluation result is returned:
- The response is validated against `ResumeEvaluationResponse` and `RubricCriterionItem`.
- All scores are verified to be finite numbers within their declared bounds (`0.0 <= score <= max_score` and `0.0 <= overall_score <= 100.0`).
- Every quote in `evidence_quotes` is checked against the candidate's actual extracted resume text. Quotes that do not match the source text are rejected and removed.
- Invalid or incomplete output returns a concise safe `HTTP 502 Bad Gateway` error and persists nothing.
- Error responses and server logs never include raw resume text, prompts, or credentials.

### 5. Local Processing vs. Cloud Inference Guarantee
- **Local Components**: Resume text extraction (PDF/DOCX), local embeddings via local Ollama with `nomic-embed-text` (768 dimensions), local Chroma vector indexing, and local semantic search remain 100% on the local machine.
- **Local Embedding Model vs. Cloud LLM**:
  - The local embedding model (`nomic-embed-text`, 768 dimensions) runs locally through Ollama (`http://127.0.0.1:11434/api/embed`) following a one-time local download (`ollama pull nomic-embed-text`). Resume text stays strictly on this device for embedding generation and is never sent to Ollama Cloud or external services.
  - In contrast, for Ollama Cloud LLMs (e.g. `gpt-oss:120b-cloud`), **no LLM weights are downloaded to your machine**; inference is executed on Ollama Cloud only when backend readiness and per-request confirmation are satisfied.

### 6. Configuring Environment Variables Safely
- **Keep Disabled (Default)**: Keep `OLLAMA_LLM_ENABLED=false`, `OLLAMA_CLOUD_USAGE_AUTHORIZED=false`, and `LLM_PROVIDER=disabled`.
- **Optional Local Testing**: Set environment variables in your local terminal session or untracked `.env` file (which is git-ignored):
  ```bash
  export LLM_PROVIDER="ollama"
  export OLLAMA_LLM_ENABLED="true"
  export OLLAMA_MODEL_NAME="gpt-oss:120b-cloud"
  export OLLAMA_CLOUD_USAGE_AUTHORIZED="true" # Authorizes token-based cloud usage (may incur charges)
  export OLLAMA_BASE_URL="http://127.0.0.1:11434" # Or your Ollama Cloud URL
  export OLLAMA_TIMEOUT_SECONDS="30.0"
  export OLLAMA_MAX_OUTPUT_TOKENS="1024"
  ```
- Never commit credentials, tokens, or account secrets to version control.


