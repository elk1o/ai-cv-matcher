"""Tests of POST /match (router). The graph is replaced by a fake: here only the preconditions
and the translation of errors into HTTP codes are tested."""
import pytest
from fastapi.testclient import TestClient

from app.graph.errors import (
    MODEL_UNAVAILABLE_MESSAGE,
    QUOTA_MESSAGE,
    ExtractionError,
    ModelQuotaError,
    ModelUnavailableError,
)
from app.main import app
from app.schemas import MatchInitialResponse, Profile, ProfileEntry
from app.services import document_store

client = TestClient(app)
USER = document_store.DEFAULT_USER


@pytest.fixture(autouse=True)
def clean_store():
    document_store._cv_texts.clear()
    document_store._offer_texts.clear()
    yield
    document_store._cv_texts.clear()
    document_store._offer_texts.clear()


def store_both():
    document_store.save_cv_text(USER, "texto del cv")
    document_store.save_offer_text(USER, "texto de la oferta")


def forbid_graph(monkeypatch):
    def forbidden(*_args):
        raise AssertionError("the graph must not run when a step is missing")

    monkeypatch.setattr("app.routers.match.build_graph", forbidden)


def test_match_requires_cv_and_offer(monkeypatch):
    forbid_graph(monkeypatch)
    assert client.post("/match").status_code == 409


def test_match_requires_the_offer_too(monkeypatch):
    forbid_graph(monkeypatch)
    document_store.save_cv_text(USER, "texto del cv")
    assert client.post("/match").status_code == 409


def test_match_requires_the_cv_too(monkeypatch):
    forbid_graph(monkeypatch)
    document_store.save_offer_text(USER, "texto de la oferta")
    assert client.post("/match").status_code == 409


def test_match_returns_thread_id_and_profile_to_review(monkeypatch):
    store_both()
    seen = {}

    def fake_graph(cv_text, offer_text):
        seen["inputs"] = (cv_text, offer_text)
        return MatchInitialResponse(thread_id="abc-123", profile=Profile(skills=[ProfileEntry(title="Python")]))

    monkeypatch.setattr("app.routers.match.build_graph", fake_graph)
    response = client.post("/match")
    assert response.status_code == 200
    body = response.json()
    assert body["thread_id"] == "abc-123"
    assert body["profile"]["skills"][0]["title"] == "Python"
    assert seen["inputs"] == ("texto del cv", "texto de la oferta")


@pytest.mark.parametrize(
    "error, status, message",
    [
        (ModelQuotaError(QUOTA_MESSAGE), 503, QUOTA_MESSAGE),
        (ModelUnavailableError(MODEL_UNAVAILABLE_MESSAGE), 503, MODEL_UNAVAILABLE_MESSAGE),
        (ExtractionError("No se pudo extraer el perfil del CV."), 502, "No se pudo extraer el perfil del CV."),
    ],
)
def test_match_translates_graph_errors_into_http_codes(monkeypatch, error, status, message):
    store_both()

    def failing(_cv, _offer):
        raise error

    monkeypatch.setattr("app.routers.match.build_graph", failing)
    response = client.post("/match")
    assert response.status_code == status
    assert response.json()["detail"] == message