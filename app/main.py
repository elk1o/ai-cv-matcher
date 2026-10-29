from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import match, profile

app = FastAPI(title="CV Matcher")

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(profile.router)

app.include_router(match.router)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")