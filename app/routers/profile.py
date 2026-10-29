from fastapi import APIRouter

router = APIRouter()

@router.delete("/profile", status_code=204)
def delete_profile():
    return None

@router.get("/profile")
def get_profile():
    return {"status": "ok profile"}