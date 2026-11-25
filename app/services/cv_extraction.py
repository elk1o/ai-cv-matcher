"""Profile extraction from a CV (PDF or DOCX).

This layer does not import anything from FastAPI: it raises its own exceptions and the
router is the one that translates them into HTTP status codes.
"""
import io
import zipfile

import docx
import pymupdf
from docx.table import Table
from docx.text.paragraph import Paragraph

MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024    # max uncompressed DOCX size (anti zip bomb)
MAX_TEXT_CHARS = 30_000 # max text length sent to the LLM

PDF_MAGIC = b"%PDF"
ZIP_MAGIC = b"PK\x03\x04"
OLE_MAGIC = b"\xd0\xcf\x11\xe0" # Word 97-2003 (.doc)

DOC_MESSAGE = "Los archivos .doc (Word antiguo) no se admiten. Guárdalo como DOCX o PDF."

class UnsupportedFileError(Exception):
    """The file is not a valid PDF or DOCX."""

class EmptyCVError(Exception):
    """The file has no extractable text (for example, a scanned PDF)."""

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