import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_FILE = DATA_DIR / "app.db"
DEFAULT_DB_URL = f"sqlite:///{DEFAULT_DB_FILE.as_posix()}"

# Read database URL from environment variable, falling back to local SQLite under backend/data/
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB_URL)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Storage directory for temporary resume staging (outside the database)
DEFAULT_STORAGE_DIR = DATA_DIR / "staged_resumes"
RESUME_STORAGE_DIR = Path(os.getenv("RESUME_STORAGE_DIR", str(DEFAULT_STORAGE_DIR)))
RESUME_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Size limits (configurable via environment, with defaults supporting batches of 50+ resumes)
# Default per-file limit: 15 MB (15 * 1024 * 1024 bytes)
# Default total-batch limit: 300 MB (300 * 1024 * 1024 bytes)
MAX_FILE_SIZE_BYTES = int(os.getenv("MAX_FILE_SIZE_BYTES", str(15 * 1024 * 1024)))
MAX_BATCH_SIZE_BYTES = int(os.getenv("MAX_BATCH_SIZE_BYTES", str(300 * 1024 * 1024)))

# ZIP Archive safety limits (configurable via environment, supporting batches of 50-100 resumes)
# Default maximum members: 200
# Default maximum total uncompressed size: 200 MB (200 * 1024 * 1024 bytes)
# Default maximum compression ratio: 100.0 (protects against zip bombs)
MAX_ZIP_MEMBERS = int(os.getenv("MAX_ZIP_MEMBERS", "200"))
MAX_ZIP_UNCOMPRESSED_SIZE_BYTES = int(os.getenv("MAX_ZIP_UNCOMPRESSED_SIZE_BYTES", str(200 * 1024 * 1024)))
MAX_ZIP_COMPRESSION_RATIO = float(os.getenv("MAX_ZIP_COMPRESSION_RATIO", "100.0"))

# Supported file extensions for resume uploads
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".zip"}

# Strict timeout for external converters (e.g., soffice or antiword)
DOC_CONVERSION_TIMEOUT_SECONDS = int(os.getenv("DOC_CONVERSION_TIMEOUT_SECONDS", "30"))

# Authentication session cookie configuration
# In production with HTTPS, set AUTH_COOKIE_SECURE=true.
# Default is False to permit local HTTP development.
AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "auth_session")
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").lower() in ("true", "1", "yes")
SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(24 * 60 * 60)))  # 24 hours default
INVITATION_MAX_AGE_SECONDS = int(os.getenv("INVITATION_MAX_AGE_SECONDS", str(7 * 24 * 60 * 60)))  # 7 days default



def get_db():
    """Minimal database session dependency for FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
