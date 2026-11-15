"""Inicio y health check."""
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from app.deps import get_current_user
from app.services.auth_service import SessionUser

router = APIRouter()

HOME_BY_ROLE = {"admin": "/admin", "teacher": "/teacher", "student": "/student"}


@router.get("/health", include_in_schema=False)
def health():
    # Lo usa el HEALTHCHECK de Docker: no depende de las bases de datos
    return {"status": "ok"}


@router.get("/")
def home(user: SessionUser = Depends(get_current_user)):
    return RedirectResponse(HOME_BY_ROLE.get(user.role, "/login"), status_code=303)
