from fastapi import APIRouter, HTTPException

from app.graph.builder import build_graph
from app.schemas import MatchInitialResponse
from app.graph.errors import ExtractionError, ModelQuotaError, ModelUnavailableError
from app.services.document_store import DEFAULT_USER, get_cv_text, get_offer_text

router = APIRouter()

@router.post("/match", response_model=MatchInitialResponse)
def match():    
    cv_text = get_cv_text(DEFAULT_USER)
    offer_text = get_offer_text(DEFAULT_USER)
    
    if cv_text is None or offer_text is None:
        raise HTTPException(status_code=409, detail="Primero sube tu CV y la oferta.")
    try:
        return build_graph(cv_text, offer_text)
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="El análisis (paso 3) aún no está implementado.")
    except ModelQuotaError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))