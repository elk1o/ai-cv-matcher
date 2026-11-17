from fastapi import APIRouter

from app.services.profile_store import DEFAULT_USER, delete_profile

router = APIRouter()


@router.delete("/profile", status_code=204)
def remove_profile():
    delete_profile(DEFAULT_USER)