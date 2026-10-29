from fastapi import APIRouter

router = APIRouter()

@router.delete("/cv", status_code=204)
def delete_cv():
    return {"status": "ok DELETE cv"}

@router.get("/cv")
def get_cv():
    return {"status": "ok GET cv"}

@router.post("/cv", status_code=200)
def post_cv():
    """
    Esto recibe un multipart con el archivo CV, extrae el perfil y no lo guarda
    """
    return {"status": "ok POST cv"}

@router.post("/cv/confirm", status_code=200)
def post_cv():
    """
    Esto guarda el perfil ya revisado por el usuario
    """
    return {"status": "ok POST cv"}