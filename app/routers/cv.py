from fastapi import APIRouter, HTTPException, UploadFile

from app.schemas import UploadResponse
from app.services.cv_extraction import EmptyCVError, UnsupportedFileError, extract_text
from app.services.document_store import DEFAULT_USER, save_cv_text

router = APIRouter()

MAX_BYTES = 5 * 1024 * 1024  # 5 MB, same as the front end

@router.post("/cv", response_model=UploadResponse)
def upload_cv(file: UploadFile):
    # Read at most MAX_BYTES + 1: that detects an oversized file without loading all of it in memory.
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="El archivo supera los 5 MB.")

    try:
        text = extract_text(data)
    except UnsupportedFileError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    except EmptyCVError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    save_cv_text(DEFAULT_USER, text)
    return UploadResponse(characters=len(text))