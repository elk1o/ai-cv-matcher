from fastapi import APIRouter

router = APIRouter()

@router.post("/match")
def match():
    return {"status": "ok POST match"}

@router.get("/match")
def match():
    return {"status": "ok GET match"}