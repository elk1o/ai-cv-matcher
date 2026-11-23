from fastapi import APIRouter, HTTPException

from app.schemas import OfferRequest, UploadResponse
from app.services.document_store import DEFAULT_USER, save_offer_text

router = APIRouter()

@router.post("/offer", response_model=UploadResponse)
def upload_offer(request: OfferRequest):
    # OfferRequest has no str_strip_whitespace: ten spaces would pass min_length=10.
    offer = request.offer.strip()
    if len(offer) < 10:
        raise HTTPException(status_code=422, detail="La oferta es demasiado corta.")
    save_offer_text(DEFAULT_USER, offer)
    return UploadResponse(characters=len(offer))