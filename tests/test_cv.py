import io
import zipfile

import docx
import pymupdf
import pytest
from fastapi.testclient import TestClient
from langchain_core.exceptions import ModelRateLimitError  # NEW (review)

from app.main import app
from app.schemas import Profile
from app.services import cv_extraction, document_store, profile_store  # NEW (review): document_store
from app.services.cv_extraction import (
    MAX_TEXT_CHARS,
    EmptyCVError,
    ExtractionError,
    ModelQuotaError,  # NEW (review)
    UnsupportedFileError,
    _EntryDraft,
    _ProfileDraft,
    detect_kind,
    extract_text,
    structure_profile,
)

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers to build files in memory
# ---------------------------------------------------------------------------
def make_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 72), text)
    return doc.tobytes()


def make_docx(paragraphs=(), table_rows=(), merge_first_row=False) -> bytes:
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    if table_rows:
        table = document.add_table(rows=len(table_rows), cols=len(table_rows[0]))
        for r, row in enumerate(table_rows):
            for c, value in enumerate(row):
                table.rows[r].cells[c].text = value
        if merge_first_row:
            table.rows[0].cells[0].merge(table.rows[0].cells[1])
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def post_cv(content: bytes, name="cv.pdf"):
    return client.post("/cv", files={"file": (name, content, "application/octet-stream")})


@pytest.fixture(autouse=True)
def clean_store():
    profile_store._profiles.clear()
    document_store._cv_texts.clear()  # NEW (review)
    document_store._offer_texts.clear()  # NEW (review)
    yield
    profile_store._profiles.clear()
    document_store._cv_texts.clear()  # NEW (review)
    document_store._offer_texts.clear()  # NEW (review)


# ---------------------------------------------------------------------------
# detect_kind
# ---------------------------------------------------------------------------
def test_detect_kind_pdf():
    assert detect_kind(make_pdf("hola")) == "pdf"


def test_detect_kind_docx():
    assert detect_kind(make_docx(["hola"])) == "docx"


def test_detect_kind_rejects_old_doc():
    with pytest.raises(UnsupportedFileError, match="DOCX"):
        detect_kind(b"\xd0\xcf\x11\xe0" + b"0" * 100)


def test_detect_kind_rejects_zip_that_is_not_docx():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("otra_cosa.txt", "hola")
    with pytest.raises(UnsupportedFileError):
        detect_kind(buffer.getvalue())


def test_detect_kind_rejects_corrupt_zip():
    with pytest.raises(UnsupportedFileError):
        detect_kind(b"PK\x03\x04" + b"basura")


@pytest.mark.parametrize("data", [b"", b"texto plano", b"\x00\x01\x02"])
def test_detect_kind_rejects_garbage(data):
    with pytest.raises(UnsupportedFileError):
        detect_kind(data)


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------
def test_extract_text_from_pdf():
    assert "Python developer" in extract_text(make_pdf("Python developer"))


def test_extract_text_pdf_without_text_raises_empty():
    with pytest.raises(EmptyCVError):
        extract_text(make_pdf(""))


def test_extract_text_from_docx_paragraph():
    assert "Python developer" in extract_text(make_docx(["Python developer"]))


def test_extract_text_from_docx_table_only():
    text = extract_text(make_docx(table_rows=[["Skills", "SQL, Git"]]))
    assert "SQL, Git" in text


def test_extract_text_docx_keeps_document_order():
    data = make_docx(["ANTES"], table_rows=[["EN_TABLA", "x"]])
    text = extract_text(data)
    assert text.index("ANTES") < text.index("EN_TABLA")


def test_extract_text_docx_merged_cell_not_duplicated():
    text = extract_text(make_docx(table_rows=[["Unica", ""], ["a", "b"]], merge_first_row=True))
    assert text.count("Unica") == 1


def test_extract_text_empty_docx_raises_empty():
    with pytest.raises(EmptyCVError):
        extract_text(make_docx())


def test_extract_text_truncates_long_text():
    text = extract_text(make_docx(["a" * (MAX_TEXT_CHARS + 500)]))
    assert len(text) == MAX_TEXT_CHARS


def test_extract_text_rejects_zip_bomb(monkeypatch):
    # Lower the limit so the test does not have to build 50 MB.
    monkeypatch.setattr(cv_extraction, "MAX_UNCOMPRESSED_BYTES", 1000)
    with pytest.raises(UnsupportedFileError):
        extract_text(make_docx(["hola"]))


# ---------------------------------------------------------------------------
# structure_profile (with a fake chain: no LLM is called)
# ---------------------------------------------------------------------------
class FakeChain:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def invoke(self, _inputs):
        if self.error:
            raise self.error
        return self.result


def make_draft(**sections) -> _ProfileDraft:
    base = {name: [] for name in _ProfileDraft.model_fields}
    base.update({k: [_EntryDraft(**e) for e in v] for k, v in sections.items()})
    return _ProfileDraft(**base)


def structure_with(monkeypatch, draft) -> Profile:
    monkeypatch.setattr(cv_extraction, "_build_chain", lambda: FakeChain(result=draft))
    return structure_profile("texto")


def test_structure_profile_returns_profile(monkeypatch):
    draft = make_draft(skills=[{"title": "Python", "detail": ""}])
    assert structure_with(monkeypatch, draft).skills[0].title == "Python"


def test_structure_profile_truncates_long_fields(monkeypatch):
    draft = make_draft(skills=[{"title": "T" * 500, "detail": "D" * 5000}])
    entry = structure_with(monkeypatch, draft).skills[0]
    assert len(entry.title) == 200
    assert len(entry.detail) == 2000


def test_structure_profile_drops_entries_without_title(monkeypatch):
    draft = make_draft(skills=[{"title": "   ", "detail": "x"}, {"title": "SQL", "detail": ""}])
    skills = structure_with(monkeypatch, draft).skills
    assert [e.title for e in skills] == ["SQL"]


def test_structure_profile_caps_entries_per_section(monkeypatch):
    draft = make_draft(skills=[{"title": f"skill {i}", "detail": ""} for i in range(80)])
    assert len(structure_with(monkeypatch, draft).skills) == 50


def test_draft_schema_has_no_limits():
    # Gemini rejects schemas with nested limits: the one we send must have none.
    schema = str(_ProfileDraft.model_json_schema())
    for keyword in ("maxItems", "minItems", "maxLength", "minLength"):
        assert keyword not in schema


def test_structure_profile_wraps_model_errors(monkeypatch):
    chain = FakeChain(error=TimeoutError("sin red"))
    monkeypatch.setattr(cv_extraction, "_build_chain", lambda: chain)
    with pytest.raises(ExtractionError):
        structure_profile("texto")


# NEW (review): test for the quota error in the service
def test_structure_profile_turns_rate_limit_into_quota_error(monkeypatch):
    error = ModelRateLimitError("429 RESOURCE_EXHAUSTED gemini-x quota")
    monkeypatch.setattr(cv_extraction, "_build_chain", lambda: FakeChain(error=error))
    with pytest.raises(ModelQuotaError) as info:
        structure_profile("texto")
    assert "RESOURCE_EXHAUSTED" not in str(info.value)  # provider details are not leaked
    assert info.value.__cause__ is error


def test_structure_profile_rejects_empty_model_output(monkeypatch):
    monkeypatch.setattr(cv_extraction, "_build_chain", lambda: FakeChain(result=None))
    with pytest.raises(ExtractionError):
        structure_profile("texto")


def test_build_chain_requires_model_name(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_MODEL"):
        cv_extraction._build_chain()


# ---------------------------------------------------------------------------
# NEW (review): POST /cv (step 1: validate, store the text, NO LLM call)
# ---------------------------------------------------------------------------
def test_upload_cv_stores_text_and_returns_length():
    response = post_cv(make_pdf("Python developer"))
    assert response.status_code == 200
    stored = document_store.get_cv_text(document_store.DEFAULT_USER)
    assert "Python developer" in stored
    assert response.json() == {"characters": len(stored)}


def test_upload_cv_accepts_docx():
    assert post_cv(make_docx(["Python developer"]), name="cv.docx").status_code == 200


def test_upload_cv_does_not_call_the_model(monkeypatch):
    def forbidden():
        raise AssertionError("the LLM must not be called in step 1")

    monkeypatch.setattr(cv_extraction, "_build_chain", forbidden)
    assert post_cv(make_pdf("Python developer")).status_code == 200


def test_upload_cv_without_file_returns_422():
    assert client.post("/cv").status_code == 422


def test_upload_cv_rejects_unsupported_file():
    assert post_cv(b"esto no es un cv").status_code == 415
    assert document_store.get_cv_text(document_store.DEFAULT_USER) is None


def test_upload_cv_rejects_file_without_text():
    assert post_cv(make_pdf("")).status_code == 422
    assert document_store.get_cv_text(document_store.DEFAULT_USER) is None


def test_upload_cv_rejects_oversized_file():
    assert post_cv(b"%PDF" + b"0" * (5 * 1024 * 1024)).status_code == 413


def test_upload_cv_replaces_previous_cv():
    post_cv(make_pdf("Primero"))
    post_cv(make_pdf("Segundo"))
    assert "Segundo" in document_store.get_cv_text(document_store.DEFAULT_USER)


# ---------------------------------------------------------------------------
# NEW (review): DELETE /profile (now also removes the raw texts)
# ---------------------------------------------------------------------------
def test_delete_profile_removes_everything():
    post_cv(make_pdf("Python developer"))
    client.post("/offer", json={"offer": "Buscamos desarrollador Python"})
    profile_store.save_profile(profile_store.DEFAULT_USER, Profile())
    assert client.delete("/profile").status_code == 204
    user = document_store.DEFAULT_USER
    assert document_store.get_cv_text(user) is None
    assert document_store.get_offer_text(user) is None
    assert profile_store.get_profile(user) is None