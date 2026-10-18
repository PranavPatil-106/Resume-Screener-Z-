# AI Resume Screener

A local-first, free-tier AI Resume Screener application.

## Project Layout

```text
.
├── .gitignore         # Ignores venvs, node_modules, local DBs, and secrets
├── README.md          # Project documentation and setup instructions
├── backend/           # FastAPI backend
│   ├── .python-version # Python version pin (3.12+)
│   ├── pyproject.toml # Backend metadata and dependencies managed by UV
│   ├── uv.lock        # UV lockfile
│   ├── database.py    # Database connection & session dependency
│   ├── models.py      # SQLAlchemy data models
│   ├── schemas.py     # Pydantic request/response schemas
│   ├── alembic/       # Alembic migrations directory
│   ├── data/          # Local SQLite storage (ignored by Git)
│   └── main.py        # FastAPI app with health and Job Descriptions APIs
└── frontend/          # React + TypeScript frontend (Vite)
    ├── package.json   # Frontend dependencies and scripts
    ├── vite.config.ts # Vite configuration
    └── src/           # React application source code
```

## Prerequisites

- [Node.js](https://nodejs.org/) (v20+) and `npm`
- [Python](https://www.python.org/) (v3.12+)
- [UV](https://github.com/astral-sh/uv) (Fast Python package manager)

## Running Locally

### 1. Backend (FastAPI + SQLAlchemy + Alembic)

Navigate to the `backend` directory:

```bash
cd backend
```

#### Database Setup & Migrations (UV)

The backend defaults to a local SQLite database under `backend/data/app.db` (ignored by Git). You can point to PostgreSQL for production by setting the `DATABASE_URL` environment variable (e.g. `postgresql+psycopg2://user:password@host/dbname`).

Apply migrations to initialize or update the database:

```bash
uv run alembic upgrade head
```

To generate a new migration after updating SQLAlchemy models:

```bash
uv run alembic revision --autogenerate -m "migration_name"
```

#### Starting the API Server

```bash
uv run uvicorn main:app --reload --port 8000
```

- API Base URL: `http://localhost:8000`
- Health Endpoint: `http://localhost:8000/health`
- Job Descriptions API: `http://localhost:8000/api/job-descriptions`
- Interactive API Docs: `http://localhost:8000/docs`

### 2. Frontend (React + Vite)

Navigate to the `frontend` directory and run using `npm`:

```bash
cd frontend
npm run dev
```

- Web App URL: `http://localhost:5173`

### 3. Authentication & First Administrator Setup

The application features local authentication with secure, expiring sessions and HTTP-only cookies:

- **Create Initial Admin Account**: No accounts or default credentials exist out of the box. Create the first admin user using the interactive command:
  ```bash
  cd backend
  uv run python create_admin.py
  ```
- **Sign In & Session Restoration**:
  - The frontend checks `GET /api/auth/me` on startup with `credentials: "include"` to automatically restore active sessions.
  - Logging in (`POST /api/auth/login`) issues an opaque session token stored in an `HttpOnly`, `SameSite=Lax` cookie and keeps only its SHA-256 hash in the database.
  - Signing out (`POST /api/auth/logout`) revokes the active session in the database and clears the cookie.
  - Tokens and passwords are never stored in `localStorage` or `sessionStorage`.
- **UI Demo Mode (Optional)**:
  - By default, `VITE_DEMO_MODE` is `false`, requiring a valid login to access the dashboard.
  - For frontend-only UI demonstration without running the backend auth database, set `VITE_DEMO_MODE=true` in your frontend environment.
- **Role-Based Access Control (RBAC)**:
  - `GET /health`, `POST /api/auth/login`, and `POST /api/auth/logout` are public.
  - `GET /api/auth/me`, `GET /api/job-descriptions`, and `GET /api/screening-sessions` require authentication; viewer accounts are restricted to viewing completed screening-session metadata only.
  - All screening workflow, staging, extraction, indexing, search, evaluation, and cleanup endpoints require `admin` or `recruiter` roles. Missing credentials return 401; insufficient roles return 403.
  - Access control is local and role-based for the single workspace; multi-tenant isolation is not claimed.

## Guarded Ollama Cloud Evaluation & Privacy Architecture

The application is built with a **local-first, fail-closed privacy architecture**. All generative AI cloud features (candidate rubric evaluation against Job Descriptions and evidence Q&A) are **strictly disabled by default**.

### 1. Disabled by Default: Required Readiness Conditions
Before any backend chat or evaluation request can be dispatched to Ollama Cloud, all three of the following conditions must be satisfied (`can_chat: true`):
1. **Provider Enabled**: `OLLAMA_LLM_ENABLED=true` (and `LLM_PROVIDER=ollama`).
2. **Model Configured**: `OLLAMA_MODEL_NAME` must be set to a non-empty model identifier (e.g., `gpt-oss:120b-cloud`).
3. **Cloud Usage Authorized**: `OLLAMA_CLOUD_USAGE_AUTHORIZED=true` (defaults to `false`).

If any of these conditions is not met, the backend returns `HTTP 503 Service Unavailable` before reading resume text or making any outbound network calls.

### 2. Cloud Usage Authorization & Billing Terms
Setting `OLLAMA_CLOUD_USAGE_AUTHORIZED=true` is an explicit opt-in authorizing token-based Ollama Cloud usage, which may incur usage charges:
- Ollama's current listed rate for `gpt-oss:120b-cloud` is $0.15 per million input tokens and $0.60 per million output tokens.
- Do not describe this setting as zero-cost verification.
- The system does not assume that the user's account has a hard spending limit or that the model is covered by a free allowance.

### 3. Dual Safeguards: Backend Readiness & Per-Request Confirmations
- **Manual Single-Resume Evaluation**:
  - Evaluation is **manual and strictly single-resume**; resumes are never evaluated automatically or in a batch.
  - Transmits only the selected candidate's extracted plain text and the linked Job Description criteria to Ollama Cloud.
  - The frontend enforces an unchecked confirmation checkbox tied explicitly to the selected resume's ID.
  - Both backend readiness (`can_chat: true`) and explicit per-resume confirmation must agree before the request is issued.
- **Evidence Chat Safeguards**:
  - Evidence chat enforces an explicit per-request confirmation checkbox before each question is submitted.
  - Clearly discloses that the question and retrieved candidate evidence chunks from the session will be sent to Ollama Cloud and may incur usage charges.
  - Enforced in the backend request schema (`confirm_cloud_transmission: bool`) as well as the UI.
  - Resets after each question so that every request requires separate manual confirmation.

### 4. Local Processing vs. Cloud Inference Guarantee
- **100% Local**: Resume staging, file text extraction (PDF/DOCX), local vector embeddings via local Ollama using `nomic-embed-text` (768 dimensions), local Chroma vector collections, and semantic search execute completely on your machine.
- **Local Embedding Model vs. Cloud LLM**:
  - The local embedding model (`nomic-embed-text`, 768 dimensions) runs entirely on your local machine using your local Ollama instance (`http://127.0.0.1:11434/api/embed`) after a one-time local download (`ollama pull nomic-embed-text`). Resume text stays on this device for embedding generation and is never sent to Ollama Cloud or external embedding APIs.
  - In contrast, for Ollama Cloud LLMs (e.g. `gpt-oss:120b-cloud`), **no LLM weights are downloaded to your machine**; inference is executed on Ollama Cloud only when backend readiness and per-request confirmation are satisfied.
- **Evaluation Persistence & Data Retention**: Validated evaluation results, rubric assessments, scores, explanations, verified evidence quotes, summaries, and related metadata persist in the local `resume_evaluations` table. Original resume files, extracted text, and Chroma vector data remain temporary and are removed when a session is completed or ended. Permanently deleting an eligible completed or ended session removes its associated evaluation records.

### 5. Configuring Environment Variables Safely
To keep cloud evaluation disabled (default recommended setup):
- Leave default settings untouched (`OLLAMA_LLM_ENABLED=false`, `OLLAMA_CLOUD_USAGE_AUTHORIZED=false`, `LLM_PROVIDER=disabled`).

To configure optional settings for local testing without committing secrets:
- Set environment variables in your local terminal session or in an untracked `.env` file (which is ignored by Git in `.gitignore`):
  ```bash
  # Example for a local Windows PowerShell session:
  $env:LLM_PROVIDER="ollama"
  $env:OLLAMA_LLM_ENABLED="true"
  $env:OLLAMA_MODEL_NAME="gpt-oss:120b-cloud"
  $env:OLLAMA_CLOUD_USAGE_AUTHORIZED="true" # Authorizes token-based cloud usage (may incur charges)
  $env:OLLAMA_BASE_URL="http://127.0.0.1:11434" # Or your configured Ollama endpoint
  ```
- Never commit API keys, credentials, or custom endpoints to source control.

