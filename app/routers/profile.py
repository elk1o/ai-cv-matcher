from fastapi import APIRouter

router = APIRouter()

@router.delete("/profile")
def delete_profile():
    """
    Este endpoint borra todo el perfil creado
    """
    return {"status": "ok DELETE cv"}