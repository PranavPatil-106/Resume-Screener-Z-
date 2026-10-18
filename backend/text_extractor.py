import io
import os
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Optional, Union

import docx
import pypdf

from database import (
    DOC_CONVERSION_TIMEOUT_SECONDS,
    MAX_ZIP_COMPRESSION_RATIO,
    MAX_ZIP_MEMBERS,
    MAX_ZIP_UNCOMPRESSED_SIZE_BYTES,
)

NESTED_ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".7z", ".rar"}
SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc"}

DOC_DEPENDENCY_REQUIRED_MSG = (
    "Text extraction for legacy .doc files requires a free local converter such as "
    "LibreOffice ('soffice') or Antiword. Neither was found installed on the system. "
    "Please install LibreOffice or Antiword, or upload .docx or .pdf."
)


def find_doc_converter() -> Optional[tuple[str, str]]:
    """
    Detect whether a free local converter (soffice/libreoffice or antiword) is installed.
    Returns (converter_type, executable_path) or None.
    """
    # 1. Check PATH for soffice or libreoffice
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return ("soffice", path)

    # 2. Check standard Windows installation paths for LibreOffice
    soffice_paths = [
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "LibreOffice" / "program" / "soffice.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "LibreOffice" / "program" / "soffice.exe",
        Path("C:\\Program Files\\LibreOffice\\program\\soffice.exe"),
        Path("C:\\Program Files (x86)\\LibreOffice\\program\\soffice.exe"),
    ]
    for p in soffice_paths:
        if p.exists() and p.is_file():
            return ("soffice", str(p))

    # 3. Check PATH for antiword
    antiword_path = shutil.which("antiword")
    if antiword_path:
        return ("antiword", antiword_path)

    # 4. Check common Windows paths for antiword
    common_antiword_paths = [
        Path("C:\\ProgramData\\chocolatey\\bin\\antiword.exe"),
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "antiword" / "antiword.exe",
    ]
    for p in common_antiword_paths:
        if p.exists() and p.is_file():
            return ("antiword", str(p))

    return None


def extract_text_from_pdf(source: Union[Path, io.BytesIO, bytes]) -> tuple[str, Optional[str]]:
    """
    Extract text from a PDF file or bytes stream using pypdf.
    Returns (extracted_text, error_message).
    """
    try:
        if isinstance(source, (bytes, bytearray)):
            stream: Union[str, io.BytesIO] = io.BytesIO(source)
        elif isinstance(source, Path):
            if not source.exists():
                return "", f"File not found: {source.name}"
            stream = str(source)
        else:
            stream = source

        reader = pypdf.PdfReader(stream)
        pages_text: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages_text.append(text.strip())
        full_text = "\n\n".join(pages_text).strip()
        return full_text, None
    except Exception as e:
        return "", f"PDF parsing error: {str(e)}"


def extract_text_from_docx(source: Union[Path, io.BytesIO, bytes]) -> tuple[str, Optional[str]]:
    """
    Extract text from a DOCX file or bytes stream using python-docx.
    Returns (extracted_text, error_message).
    """
    try:
        if isinstance(source, (bytes, bytearray)):
            stream: Union[str, io.BytesIO] = io.BytesIO(source)
        elif isinstance(source, Path):
            if not source.exists():
                return "", f"File not found: {source.name}"
            stream = str(source)
        else:
            stream = source

        doc = docx.Document(stream)
        text_parts: list[str] = []
        for paragraph in doc.paragraphs:
            text = paragraph.text.strip()
            if text:
                text_parts.append(text)
        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    text_parts.append(" | ".join(cells))
        full_text = "\n\n".join(text_parts).strip()
        return full_text, None
    except Exception as e:
        return "", f"DOCX parsing error: {str(e)}"


def extract_text_from_doc(source: Union[Path, io.BytesIO, bytes]) -> tuple[str, Optional[str]]:
    """
    Extract text from a legacy .doc file using an available local converter (LibreOffice or Antiword).
    Safely executes via subprocess argument arrays (never shell=True), in an isolated temporary
    directory with a generated uuid filename, enforces a strict timeout, and cleans up in finally.
    Returns (extracted_text, error_message).
    """
    converter_info = find_doc_converter()
    if not converter_info:
        return "", DOC_DEPENDENCY_REQUIRED_MSG

    converter_type, converter_bin = converter_info

    # Read binary content
    if isinstance(source, (bytes, bytearray)):
        doc_bytes = bytes(source)
    elif isinstance(source, Path):
        if not source.exists():
            return "", f"File not found: {source.name}"
        try:
            doc_bytes = source.read_bytes()
        except Exception as e:
            return "", f"Failed to read .doc file: {str(e)}"
    elif isinstance(source, io.BytesIO):
        doc_bytes = source.getvalue()
    else:
        return "", "Invalid source format for .doc extraction."

    if len(doc_bytes) == 0:
        return "", "Empty file: document contains 0 bytes."

    temp_dir = tempfile.mkdtemp(prefix="doc_conv_")
    try:
        # Use a randomly generated uuid filename (never archive-supplied paths)
        temp_input_filename = f"{uuid.uuid4().hex}.doc"
        temp_input_path = Path(temp_dir) / temp_input_filename
        temp_input_path.write_bytes(doc_bytes)

        if converter_type == "soffice":
            # libreoffice --headless --convert-to txt:Text --outdir <temp_dir> <temp_input>
            cmd = [
                converter_bin,
                "--headless",
                "--convert-to",
                "txt:Text",
                "--outdir",
                temp_dir,
                str(temp_input_path),
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=DOC_CONVERSION_TIMEOUT_SECONDS,
                    shell=False,
                )
            except subprocess.TimeoutExpired:
                return "", f"Conversion timed out after {DOC_CONVERSION_TIMEOUT_SECONDS} seconds."
            except Exception as e:
                return "", f"Converter execution failed: {str(e)}"

            if proc.returncode != 0:
                err_msg = proc.stderr.strip() or f"Converter exited with code {proc.returncode}"
                return "", f"LibreOffice conversion failed: {err_msg}"

            expected_output = Path(temp_dir) / f"{temp_input_path.stem}.txt"
            if not expected_output.exists():
                return "", "LibreOffice did not produce text output (file may be corrupt or unreadable)."

            try:
                text = expected_output.read_text(encoding="utf-8", errors="replace").strip()
                return text, None
            except Exception as e:
                return "", f"Failed to read converted text: {str(e)}"

        elif converter_type == "antiword":
            # antiword <temp_input>
            cmd = [converter_bin, str(temp_input_path)]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=DOC_CONVERSION_TIMEOUT_SECONDS,
                    shell=False,
                )
            except subprocess.TimeoutExpired:
                return "", f"Antiword timed out after {DOC_CONVERSION_TIMEOUT_SECONDS} seconds."
            except Exception as e:
                return "", f"Antiword execution failed: {str(e)}"

            if proc.returncode != 0:
                err_msg = proc.stderr.strip() or f"Antiword exited with code {proc.returncode}"
                return "", f"Antiword conversion failed: {err_msg}"

            return proc.stdout.strip(), None

        else:
            return "", f"Unsupported converter type: {converter_type}"

    finally:
        # Strict cleanup in finally
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


def is_safe_member_path(name: str) -> bool:
    """
    Validate that an archive member path does not attempt path traversal
    or access absolute/system directories.
    """
    if "\x00" in name:
        return False
    if len(name) > 1 and name[1] == ":":
        return False
    if name.startswith("/") or name.startswith("\\"):
        return False
    parts = Path(name).parts
    if ".." in parts:
        return False
    return True


def extract_text_from_zip(file_path: Path) -> tuple[str, str, Optional[str]]:
    """
    Safely extract text from PDF, DOCX, and supported DOC members inside a staged ZIP archive in-memory.
    Never writes extracted members to the filesystem using archive-supplied paths.
    Enforces member count, uncompressed size, and compression ratio limits.
    Returns (status, extracted_text, concise_error_message).
    """
    if not file_path.exists():
        return "failed", "", f"Archive file not found: {file_path.name}"

    if not zipfile.is_zipfile(file_path):
        return "failed", "", "File is not a valid ZIP archive or is corrupt."

    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            members = zf.infolist()

            # 1. Check member count limit
            if len(members) > MAX_ZIP_MEMBERS:
                return (
                    "failed",
                    "",
                    f"Archive member count ({len(members)}) exceeds limit of {MAX_ZIP_MEMBERS}.",
                )

            # 2. Check total uncompressed size and compression ratio limits
            total_uncompressed = sum(m.file_size for m in members)
            total_compressed = sum(m.compress_size for m in members)

            if total_uncompressed > MAX_ZIP_UNCOMPRESSED_SIZE_BYTES:
                return (
                    "failed",
                    "",
                    f"Archive uncompressed size ({total_uncompressed} bytes) exceeds limit of "
                    f"{MAX_ZIP_UNCOMPRESSED_SIZE_BYTES} bytes ({MAX_ZIP_UNCOMPRESSED_SIZE_BYTES // (1024 * 1024)} MB).",
                )

            ratio = total_uncompressed / max(total_compressed, 1)
            if ratio > MAX_ZIP_COMPRESSION_RATIO:
                return (
                    "failed",
                    "",
                    f"Archive compression ratio ({ratio:.1f}) exceeds safety limit ({MAX_ZIP_COMPRESSION_RATIO}).",
                )

            # 3. Check for encryption / password-protection
            for m in members:
                if m.flag_bits & 0x1:
                    return "failed", "", "Archive contains encrypted or password-protected files."

            converter_info = find_doc_converter()
            has_doc_converter = converter_info is not None

            doc_member_count = 0
            supported_count = 0
            extracted_blocks: list[str] = []

            # 4. Iterate members in-memory without filesystem extraction
            for member in members:
                # Ignore directories
                if member.is_dir() or member.filename.endswith("/") or member.filename.endswith("\\"):
                    continue

                # Validate member path for safety
                if not is_safe_member_path(member.filename):
                    continue

                member_ext = Path(member.filename).suffix.lower()

                # Ignore nested archives
                if member_ext in NESTED_ARCHIVE_EXTENSIONS:
                    continue

                if member_ext not in SUPPORTED_DOCUMENT_EXTENSIONS:
                    continue

                if member_ext == ".doc":
                    doc_member_count += 1
                    if not has_doc_converter:
                        # Skip conversion if converter is not installed
                        continue

                supported_count += 1
                member_clean_name = Path(member.filename).name

                try:
                    member_bytes = zf.read(member)
                except RuntimeError as re:
                    if "encrypted" in str(re).lower() or "password" in str(re).lower():
                        return "failed", "", "Archive contains encrypted or password-protected files."
                    return "failed", "", f"Failed to read archive member '{member_clean_name}': {str(re)}"

                if member_ext == ".pdf":
                    text, err = extract_text_from_pdf(member_bytes)
                elif member_ext == ".docx":
                    text, err = extract_text_from_docx(member_bytes)
                elif member_ext == ".doc":
                    text, err = extract_text_from_doc(member_bytes)
                else:
                    text, err = "", None

                if text and text.strip():
                    extracted_blocks.append(
                        f"=== File: {member_clean_name} ===\n{text.strip()}"
                    )

            if supported_count == 0:
                if doc_member_count > 0 and not has_doc_converter:
                    return (
                        "unsupported",
                        "",
                        "Archive contains legacy .doc files, but text extraction requires LibreOffice ('soffice') or Antiword, which is not installed.",
                    )
                return (
                    "unsupported",
                    "",
                    "No supported PDF or DOCX documents found in archive.",
                )

            if not extracted_blocks:
                return (
                    "empty",
                    "",
                    "Supported documents in archive contained no extractable text.",
                )

            combined_text = "\n\n".join(extracted_blocks).strip()
            return "extracted", combined_text, None

    except zipfile.BadZipFile as e:
        return "failed", "", f"Corrupt ZIP archive: {str(e)}"
    except Exception as e:
        return "failed", "", f"Error processing ZIP archive: {str(e)}"


def extract_zip_members(file_path: Path) -> tuple[str, list[tuple[str, str, str]], Optional[str]]:
    """
    Extract each supported member of a ZIP archive as its OWN document (one candidate per file).
    Same safety limits as extract_text_from_zip (member count, uncompressed size, ratio, encryption,
    path traversal, nested archives). Nothing is written to disk.
    Returns (status, members, error) where members is a list of (clean_filename, extension, text).
    status is 'extracted' when at least one member had text, else 'empty'/'unsupported'/'failed'.
    """
    if not file_path.exists():
        return "failed", [], f"Archive file not found: {file_path.name}"
    if not zipfile.is_zipfile(file_path):
        return "failed", [], "File is not a valid ZIP archive or is corrupt."

    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ZIP_MEMBERS:
                return "failed", [], f"Archive member count ({len(infos)}) exceeds limit of {MAX_ZIP_MEMBERS}."
            total_unc = sum(m.file_size for m in infos)
            total_cmp = sum(m.compress_size for m in infos)
            if total_unc > MAX_ZIP_UNCOMPRESSED_SIZE_BYTES:
                return "failed", [], "Archive uncompressed size exceeds the configured limit."
            if total_unc / max(total_cmp, 1) > MAX_ZIP_COMPRESSION_RATIO:
                return "failed", [], "Archive compression ratio exceeds the safety limit."
            if any(m.flag_bits & 0x1 for m in infos):
                return "failed", [], "Archive contains encrypted or password-protected files."

            has_doc_converter = find_doc_converter() is not None
            results: list[tuple[str, str, str]] = []
            seen_supported = 0
            skipped_doc = 0

            for member in infos:
                if member.is_dir() or member.filename.endswith(("/", "\\")):
                    continue
                if not is_safe_member_path(member.filename):
                    continue
                name = Path(member.filename).name
                if name.startswith(".") or member.filename.startswith("__MACOSX"):
                    continue
                ext = Path(name).suffix.lower()
                if ext in NESTED_ARCHIVE_EXTENSIONS or ext not in SUPPORTED_DOCUMENT_EXTENSIONS:
                    continue
                if ext == ".doc" and not has_doc_converter:
                    skipped_doc += 1
                    continue
                seen_supported += 1
                try:
                    data = zf.read(member)
                except Exception:  # noqa: BLE001
                    continue
                if ext == ".pdf":
                    text, _ = extract_text_from_pdf(data)
                elif ext == ".docx":
                    text, _ = extract_text_from_docx(data)
                else:
                    text, _ = extract_text_from_doc(data)
                if text and text.strip():
                    results.append((name, ext, text.strip()))

            if seen_supported == 0:
                if skipped_doc:
                    return "unsupported", [], "Archive contains only legacy .doc files and no converter is installed."
                return "unsupported", [], "No supported PDF or DOCX documents found in archive."
            if not results:
                return "empty", [], "Supported documents in archive contained no extractable text."
            return "extracted", results, None
    except zipfile.BadZipFile as e:
        return "failed", [], f"Corrupt ZIP archive: {str(e)}"
    except Exception as e:  # noqa: BLE001
        return "failed", [], f"Error processing ZIP archive: {str(e)}"


def extract_resume_text(file_path: Path, file_type: str) -> tuple[str, str, Optional[str]]:
    """
    Extract text based on file extension.
    Returns (status, extracted_text, concise_error_message).
    Statuses: 'extracted', 'empty', 'failed', 'unsupported'.
    """
    ext = file_type.lower()
    if not ext.startswith("."):
        ext = f".{ext}"

    if ext == ".pdf":
        text, err = extract_text_from_pdf(file_path)
        if err:
            return "failed", "", err
        if not text:
            return "empty", "", "No extractable text found in PDF document (may be blank or an image-only scan)."
        return "extracted", text, None

    if ext == ".docx":
        text, err = extract_text_from_docx(file_path)
        if err:
            return "failed", "", err
        if not text:
            return "empty", "", "No extractable text found in DOCX document."
        return "extracted", text, None

    if ext == ".doc":
        converter_info = find_doc_converter()
        if not converter_info:
            return "unsupported", "", DOC_DEPENDENCY_REQUIRED_MSG

        text, err = extract_text_from_doc(file_path)
        if err:
            return "failed", "", err
        if not text:
            return "empty", "", "No extractable text found in .doc document."
        return "extracted", text, None

    if ext == ".zip":
        return extract_text_from_zip(file_path)

    return "unsupported", "", f"Text extraction is not supported for '{ext}' files."
