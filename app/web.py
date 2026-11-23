"""Utilidades web: plantillas, CSRF, mensajes flash y validación de formularios."""
import secrets
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ValidationError

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))  # autoescape activo

ROLE_LABELS = {"admin": "Administrador", "teacher": "Docente", "student": "Estudiante"}
templates.env.globals["role_labels"] = ROLE_LABELS

CSRF_KEY = "csrf_token"
FLASH_KEY = "_flash"


# ---------- CSRF (patrón "synchronizer token") ----------
def get_csrf_token(request: Request) -> str:
    """Un token aleatorio por sesión; va oculto en cada formulario."""
    token = request.session.get(CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_KEY] = token
    return token


def _check_csrf(request: Request, sent) -> None:
    expected = request.session.get(CSRF_KEY)
    if not expected or not isinstance(sent, str) or not secrets.compare_digest(sent, expected):
        raise HTTPException(status_code=403, detail="Token CSRF inválido. Recarga la página e intenta de nuevo.")


async def read_form(request: Request) -> dict[str, str]:
    """Lee un formulario POST y verifica el token CSRF. Úsala en TODOS los POST."""
    form = await request.form()
    _check_csrf(request, form.get(CSRF_KEY))
    return {k: v for k, v in form.multi_items() if isinstance(v, str) and k != CSRF_KEY}


async def read_upload_form(request: Request, max_files: int = 1, max_fields: int = 10):
    """Igual que read_form, pero para multipart/form-data con archivos.
    Devuelve (campos_de_texto, formulario). Quien llama DEBE cerrar: await form.close()"""
    # max_files / max_fields: límites del parser de Starlette (evitan abuso del formulario)
    form = await request.form(max_files=max_files, max_fields=max_fields)
    try:
        _check_csrf(request, form.get(CSRF_KEY))
    except HTTPException:
        await form.close()  # borra el archivo temporal antes de rechazar
        raise
    data = {k: v for k, v in form.multi_items() if isinstance(v, str) and k != CSRF_KEY}
    return data, form


# ---------- Mensajes flash ----------
def flash(request: Request, message: str, category: str = "info") -> None:
    request.session.setdefault(FLASH_KEY, []).append([category, message])


# ---------- Renderizado ----------
def render(request: Request, template: str, context: dict | None = None, status_code: int = 200):
    ctx = {
        "csrf_token": get_csrf_token(request),
        "messages": request.session.pop(FLASH_KEY, []),
        "current_user": getattr(request.state, "user", None),
    }
    ctx.update(context or {})
    return templates.TemplateResponse(request, template, ctx, status_code=status_code)


def render_error(request: Request, status_code: int, title: str, message: str):
    """Página de error sin tocar la sesión (sirve también para errores 500)."""
    ctx = {"title": title, "message": message, "status_code": status_code,
           "current_user": None, "csrf_token": None, "messages": []}
    return templates.TemplateResponse(request, "error.html", ctx, status_code=status_code)


# ---------- Validación ----------
def validate(model_cls: type[BaseModel], data: dict):
    """Devuelve (modelo, None) si es válido o (None, mensaje) si no."""
    try:
        return model_cls.model_validate(data), None
    except ValidationError as exc:
        return None, format_errors(exc)


def format_errors(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err["loc"]) or "formulario"
        parts.append(f"{field}: {err['msg']}")
    return "; ".join(parts)


def parse_optional_int(value: str | None) -> int | None:
    """Convierte un parámetro de URL/formulario a entero positivo (o None si viene vacío)."""
    if value is None or str(value).strip() == "":
        return None
    try:
        number = int(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Parámetro numérico inválido.")
    if number <= 0:
        raise HTTPException(status_code=400, detail="Parámetro numérico inválido.")
    return number


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
