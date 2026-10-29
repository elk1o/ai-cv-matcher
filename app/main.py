from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="CV Matcher")

@app.get("/health")
def health():
    return {"status": "ok"}

# SIEMPRE al final: un mount en "/" captura todo lo que no coincida antes
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")