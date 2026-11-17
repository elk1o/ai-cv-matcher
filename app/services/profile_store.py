"""Temporary in-memory store for the confirmed profile.

Provisional: it is lost on restart and there are no users yet (everything goes to DEFAULT_USER).
It will be replaced by real persistence and per-user_id isolation.
"""
from app.schemas import Profile

DEFAULT_USER = "anonymous"

_profiles: dict[str, Profile] = {}


def save_profile(user_id: str, profile: Profile) -> None:
    _profiles[user_id] = profile


def get_profile(user_id: str) -> Profile | None:
    return _profiles.get(user_id)


def delete_profile(user_id: str) -> None:
    _profiles.pop(user_id, None)