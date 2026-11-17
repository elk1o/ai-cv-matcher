"""Profile extraction from a CV (PDF or DOCX).

This layer does not import anything from FastAPI: it raises its own exceptions and the
router is the one that translates them into HTTP status codes.
"""
import io
import logging
import os
import zipfile

import docx
import pymupdf
from docx.table import Table
from docx.text.paragraph import Paragraph
from langchain_core.exceptions import ModelRateLimitError
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from app.schemas import Profile
from app.prompts import CV_EXTRACTION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 30_000                      # max text length sent to the LLM
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024    # max uncompressed DOCX size (anti zip bomb)

# Limits of Profile (app/schemas.py). Keep in sync: if they change there, change them here.
MAX_TITLE_CHARS = 200
MAX_DETAIL_CHARS = 2000
MAX_ENTRIES_PER_SECTION = 50

PDF_MAGIC = b"%PDF"
ZIP_MAGIC = b"PK\x03\x04"
OLE_MAGIC = b"\xd0\xcf\x11\xe0"  # Word 97-2003 (.doc)

DOC_MESSAGE = "Los archivos .doc (Word antiguo) no se admiten. Guárdalo como DOCX o PDF."

class _EntryDraft(BaseModel):
    """Entry as returned by the LLM. No limits: Gemini rejects schemas with many nested
    limits ("too many states for serving")."""

    title: str
    detail: str

class _ProfileDraft(BaseModel):
    """Schema sent to the LLM. The limits are applied afterwards, in _to_profile."""

    experience: list[_EntryDraft]
    education: list[_EntryDraft]
    courses: list[_EntryDraft]
    skills: list[_EntryDraft]
    languages: list[_EntryDraft]
    achievements: list[_EntryDraft]

class UnsupportedFileError(Exception):
    """The file is not a valid PDF or DOCX."""

class EmptyCVError(Exception):
    """The file has no extractable text (for example, a scanned PDF)."""

class ModelQuotaError(Exception):
    """The model provider's quota or rate limit is exhausted (not the user's fault)."""

class ExtractionError(Exception):
    """The model did not return a valid profile."""

# ---------------------------------------------------------------------------
# 1. Detect the file type from its content (not from its name)
# ---------------------------------------------------------------------------
def detect_kind(data: bytes) -> str:
    """Return "pdf" or "docx", or raise UnsupportedFileError."""
    if data.startswith(PDF_MAGIC):
        return "pdf"
    if data.startswith(OLE_MAGIC):
        raise UnsupportedFileError(DOC_MESSAGE)
    if data.startswith(ZIP_MAGIC):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if "word/document.xml" in archive.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            pass
    raise UnsupportedFileError("El archivo debe ser un PDF o un DOCX.")


# ---------------------------------------------------------------------------
# 2. Extract the text
# ---------------------------------------------------------------------------
def _pdf_to_text(data: bytes) -> str:
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass:
                raise UnsupportedFileError("El PDF está protegido con contraseña.")
            # sort=True orders blocks top to bottom and left to right,
            # which helps with two-column CVs.
            return "\n".join(page.get_text("text", sort=True) for page in doc)
    except UnsupportedFileError:
        raise
    except Exception as exc:  # corrupt or unreadable PDF
        raise UnsupportedFileError("No se pudo leer el PDF.") from exc


def _table_lines(table: Table) -> list[str]:
    lines = []
    for row in table.rows:
        seen = set()
        cells = []
        for cell in row.cells:
            # A merged cell shows up repeated in row.cells: count it only once.
            if id(cell._tc) in seen:
                continue
            seen.add(id(cell._tc))
            text = cell.text.strip()
            if text:
                cells.append(text)
        if cells:
            lines.append(" | ".join(cells))
    return lines


def _docx_to_text(data: bytes) -> str:
    try:
        # A DOCX is a ZIP: check how big it would be uncompressed BEFORE opening it.
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            total = sum(info.file_size for info in archive.infolist())
        if total > MAX_UNCOMPRESSED_BYTES:
            raise UnsupportedFileError("El DOCX es demasiado grande.")

        document = docx.Document(io.BytesIO(data))
        lines: list[str] = []
        # iter_inner_content keeps the document order (paragraphs and tables mixed).
        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                lines.append(block.text)
            elif isinstance(block, Table):
                lines.extend(_table_lines(block))
        return "\n".join(lines)
    except UnsupportedFileError:
        raise
    except Exception as exc:  # corrupt ZIP or XML
        raise UnsupportedFileError("No se pudo leer el DOCX.") from exc


def extract_text(data: bytes) -> str:
    kind = detect_kind(data)
    text = _pdf_to_text(data) if kind == "pdf" else _docx_to_text(data)
    text = text.strip()
    if not text:
        raise EmptyCVError("El archivo no contiene texto.")
    return text[:MAX_TEXT_CHARS]


# ---------------------------------------------------------------------------
# 3. Structure the text into a Profile with the LLM
# ---------------------------------------------------------------------------
def _build_chain():
    # Lazy import: faster startup, and the tests do not need the Google SDK.
    from langchain_google_genai import ChatGoogleGenerativeAI

    model = os.environ.get("GEMINI_MODEL")
    if not model:
        raise RuntimeError("Falta la variable de entorno GEMINI_MODEL.")

    prompt = ChatPromptTemplate.from_messages(
        [("system", CV_EXTRACTION_SYSTEM_PROMPT), ("human", "<cv>\n{cv_text}\n</cv>")]
    )
    llm = ChatGoogleGenerativeAI(model=model)
    return prompt | llm.with_structured_output(_ProfileDraft)


def _clean_entries(entries: list[_EntryDraft]) -> list[dict]:
    cleaned = []
    for entry in entries:
        title = entry.title.strip()[:MAX_TITLE_CHARS].strip()
        if not title:  # an entry without a title is useless
            continue
        cleaned.append({"title": title, "detail": entry.detail.strip()[:MAX_DETAIL_CHARS]})
    return cleaned[:MAX_ENTRIES_PER_SECTION]


def _to_profile(draft: _ProfileDraft) -> Profile:
    """Apply the limits to the LLM draft and validate it as a Profile.

    Fields are truncated instead of rejected: a 201-character title does not justify a 502.
    """
    data = {name: _clean_entries(getattr(draft, name)) for name in _ProfileDraft.model_fields}
    return Profile.model_validate(data)


def structure_profile(text: str) -> Profile:
    chain = _build_chain()
    try:
        result = chain.invoke({"cv_text": text})
        draft = _ProfileDraft.model_validate(result)
        return _to_profile(draft)
    except ModelRateLimitError as exc:
        # Must go before `except Exception`: Python uses the first clause that matches.
        # The provider message (model, project, quota URLs) is logged, never sent to the user.
        logger.warning("Model quota exceeded: %s", type(exc).__name__)
        raise ModelQuotaError(
            "El servicio ha alcanzado su límite de uso. Inténtalo de nuevo más tarde."
        ) from exc
    except Exception as exc:
        # Invalid output, network or quota failure...
        # The CV text is deliberately left out of the message (personal data).
        raise ExtractionError("No se pudo extraer el perfil del CV.") from exc