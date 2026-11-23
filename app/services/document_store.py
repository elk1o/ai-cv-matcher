"""Temporary in-memory store for the raw texts of the current analysis (CV and job offer).

Provisional, like profile_store: it is lost on restart and there are no users yet
(everything goes to DEFAULT_USER). The CV text is personal data: it is only kept so that
step 3 (the graph) can read it, and DELETE /profile removes it.
"""
from app.services.profile_store import DEFAULT_USER  # noqa: F401  (re-exported for the routers)

_cv_texts: dict[str, str] = {}
_offer_texts: dict[str, str] = {}


def save_cv_text(user_id: str, text: str) -> None:
    _cv_texts[user_id] = text


def get_cv_text(user_id: str) -> str | None:
    return _cv_texts.get(user_id)


def save_offer_text(user_id: str, text: str) -> None:
    _offer_texts[user_id] = text


def get_offer_text(user_id: str) -> str | None:
    return _offer_texts.get(user_id)


def delete_documents(user_id: str) -> None:
    _cv_texts.pop(user_id, None)
    _offer_texts.pop(user_id, None)