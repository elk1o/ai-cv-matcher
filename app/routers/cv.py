from fastapi import APIRouter, HTTPException, UploadFile

from app.schemas import ProfileConfirmRequest, ProfileResponse
from app.services.cv_extraction import (
    EmptyCVError,
    ExtractionError,
    ModelQuotaError,
    UnsupportedFileError,
    extract_text,
    structure_profile,
)
from app.services.profile_store import DEFAULT_USER, save_profile

router = APIRouter()

MAX_BYTES = 5 * 1024 * 1024  # 5 MB, same as the frontend


@router.post("/cv", response_model=ProfileResponse)
def upload_cv(file: UploadFile):
    # Read at most MAX_BYTES + 1: this detects oversize files without loading everything in memory.
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="El archivo supera los 5 MB.")

    try:
        text = extract_text(data)
        profile = structure_profile(text)
    except UnsupportedFileError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    except EmptyCVError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ModelQuotaError as exc:
        # 503, not 429: the app's shared quota is exhausted, the user did nothing wrong.
        raise HTTPException(status_code=503, detail=str(exc))
    except ExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Nothing is saved: the user reviews the profile and confirms it at /cv/confirm.
    return ProfileResponse(profile=profile)

@router.post("/cv/confirm", status_code=204)
def confirm_profile(request: ProfileConfirmRequest):
    save_profile(DEFAULT_USER, request.profile)