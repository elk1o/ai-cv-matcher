# NEW (review): tests for POST /offer (step 2: validate and store the text, NO LLM call)
import pytest
from fastapi.testclient import TestClient

from app.main import app
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


def test_upload_offer_stores_text_and_returns_length():
    response = client.post("/offer", json={"offer": "Buscamos desarrollador Python"})
    assert response.status_code == 200
    assert response.json() == {"characters": len("Buscamos desarrollador Python")}
    assert document_store.get_offer_text(USER) == "Buscamos desarrollador Python"


def test_upload_offer_strips_surrounding_whitespace():
    client.post("/offer", json={"offer": "   Buscamos desarrollador Python   "})
    assert document_store.get_offer_text(USER) == "Buscamos desarrollador Python"


@pytest.mark.parametrize("offer", ["corta", "          ", " " * 5 + "abc" + " " * 5])
def test_upload_offer_rejects_too_short_text(offer):
    response = client.post("/offer", json={"offer": offer})
    assert response.status_code == 422
    assert document_store.get_offer_text(USER) is None


def test_upload_offer_rejects_too_long_text():
    assert client.post("/offer", json={"offer": "a" * 8001}).status_code == 422


def test_upload_offer_without_body_returns_422():
    assert client.post("/offer").status_code == 422


def test_upload_offer_replaces_previous_offer():
    client.post("/offer", json={"offer": "Primera oferta de prueba"})
    client.post("/offer", json={"offer": "Segunda oferta de prueba"})
    assert document_store.get_offer_text(USER) == "Segunda oferta de prueba"