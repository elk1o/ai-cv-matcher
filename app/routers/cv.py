from fastapi import APIRouter, UploadFile
from app.schemas import ProfileResponse

router = APIRouter()

@router.delete("/cv", status_code=204)
def delete_cv():
    return {"status": "ok DELETE cv"}

@router.get("/cv")
def get_cv():
    return {"status": "ok GET cv"}

@router.post("/cv", response_model=ProfileResponse)
def upload_cv(file: UploadFile):
    """
    Esto recibe un multipart con el archivo CV, extrae el perfil y no lo guarda
    """
    pass

@router.post("/cv/confirm", status_code=200)
def post_cv():
    """
    Esto guarda el perfil ya revisado por el usuario
    """
    return {"status": "ok POST cv"}