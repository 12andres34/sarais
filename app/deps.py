"""Dependencias de autorización. La regla se aplica en el SERVIDOR en cada petición."""
import time

from fastapi import Depends, HTTPException, Request
from sqlalchemy.engine import Connection

from app.config import get_settings
from app.db import get_db
from app.services.auth_service import SessionUser, load_session_user


def session_user_id(request: Request) -> int:
    """Revisa la cookie ANTES de abrir conexión a MySQL (anónimos no tocan la BD)."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)  # el manejador redirige a /login

    # Cierre de sesión por inactividad
    now = int(time.time())
    if now - int(request.session.get("last_seen", 0)) > get_settings().session_idle_minutes * 60:
        request.session.clear()
        raise HTTPException(status_code=401)
    request.session["last_seen"] = now
    return int(user_id)


def get_current_user(request: Request, user_id: int = Depends(session_user_id),
                     db: Connection = Depends(get_db)) -> SessionUser:
    user = load_session_user(db, user_id)
    if user is None:  # borrado o desactivado
        request.session.clear()
        raise HTTPException(status_code=401)
    request.state.user = user  # para mostrar el menú en las plantillas
    return user


def require_role(*roles: str):
    """Uso: user = Depends(require_role("admin")). Debe ir ANTES que db en la firma."""
    def checker(user: SessionUser = Depends(get_current_user)) -> SessionUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="No tienes permiso para ver esta página.")
        return user
    return checker


ADMIN = require_role("admin")
TEACHER = require_role("teacher")
STUDENT = require_role("student")
