# NEW (review): tests for POST /match (step 3). The graph does not exist yet: here only the
# router is tested (preconditions and translation of errors). The graph gets its own tests.
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import OfferRequirement, OfferResponse
from app.services import document_store
from app.services.cv_extraction import ExtractionError, ModelQuotaError

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


def test_match_requires_cv_and_offer():
    assert client.post("/match").status_code == 409


def test_match_requires_the_offer_too():
    document_store.save_cv_text(USER, "texto del cv")
    assert client.post("/match").status_code == 409


def test_match_requires_the_cv_too():
    document_store.save_offer_text(USER, "texto de la oferta")
    assert client.post("/match").status_code == 409


def test_match_returns_501_while_the_graph_is_not_built():
    store_both()
    assert client.post("/match").status_code == 501


def test_match_returns_the_graph_result(monkeypatch):
    store_both()
    result = OfferResponse(
        score=50,
        requirements=[OfferRequirement(text="Python", status="Partial", evidence="2 años")],
    )
    seen = {}

    def fake_run(cv_text, offer_text):
        seen["inputs"] = (cv_text, offer_text)
        return result

    monkeypatch.setattr("app.routers.match.run_match", fake_run)
    response = client.post("/match")
    assert response.status_code == 200
    assert response.json()["score"] == 50
    assert seen["inputs"] == ("texto del cv", "texto de la oferta")


def test_match_returns_503_when_quota_exhausted(monkeypatch):
    store_both()

    def exhausted(_cv, _offer):
        raise ModelQuotaError("El servicio ha alcanzado su límite de uso.")

    monkeypatch.setattr("app.routers.match.run_match", exhausted)
    response = client.post("/match")
    assert response.status_code == 503
    assert "límite de uso" in response.json()["detail"]


def test_match_returns_502_when_the_model_fails(monkeypatch):
    store_both()

    def failing(_cv, _offer):
        raise ExtractionError("No se pudo extraer el perfil del CV.")

    monkeypatch.setattr("app.routers.match.run_match", failing)
    assert client.post("/match").status_code == 502