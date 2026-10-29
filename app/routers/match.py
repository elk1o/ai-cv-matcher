from fastapi import APIRouter

router = APIRouter()

@router.post("/match")
def match():
    return {"score": 0, "requirements": []}

@router.get("/match")
def match():
    return {"status": "ok match"}