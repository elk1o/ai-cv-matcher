from fastapi import APIRouter

from app.services.document_store import DEFAULT_USER, delete_documents
from app.services.profile_store import delete_profile

router = APIRouter()

@router.delete("/profile", status_code=204)
def remove_profile():
    delete_profile(DEFAULT_USER)
    delete_documents(DEFAULT_USER)