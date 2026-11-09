from fastapi import APIRouter

router = APIRouter()

@router.post("/offer")
def offer():
    return {"status": "ok POST offer"}
 
@router.get("/offer")
def offer():
    return {"status": "ok GET offer"}