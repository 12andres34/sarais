"""Punto de entrada: uvicorn app.main:app (desde /srv)."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app import security
from app.config import get_settings
from app.routers import admin, auth, documents, pages, student, teacher
from app.web import BASE_DIR, render_error

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("sarais")

# Cabeceras de seguridad. CSP sin 'unsafe-inline': no usar <script> ni style="" en plantillas
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'",
}

ERROR_TITLES = {
    400: ("Solicitud inválida", "Revisa los datos enviados."),
    403: ("Acceso denegado", "No tienes permiso para realizar esta acción."),
    404: ("Página no encontrada", "La dirección no existe."),
    405: ("Método no permitido", "Esta acción no está disponible."),
    413: ("Archivo demasiado grande", "El archivo supera el tamaño máximo permitido."),
}


def create_app() -> FastAPI:
    settings = get_settings()

    # Protección: el stub de seguridad nunca debe llegar a producción
    if getattr(security, "IS_STUB", False):
        if settings.is_production:
            raise RuntimeError("app/security es un STUB: falta el módulo de seguridad.")
        logger.warning("*** Usando STUB de app/security: solo para desarrollo ***")

    # Sin /docs ni /openapi.json: menos superficie de ataque
    app = FastAPI(title="SARAIS", docs_url=None, redoc_url=None, openapi_url=None)

    # Cookie de sesión firmada: HttpOnly (siempre en Starlette), Secure y SameSite=Strict
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="sarais_session",
        max_age=settings.session_max_age_seconds,
        same_site="strict",
        https_only=settings.cookie_secure,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if not request.url.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "no-store")  # no guardar datos personales en caché
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 401:
            return RedirectResponse("/login", status_code=303)
        title, message = ERROR_TITLES.get(exc.status_code, ("Error", "Ocurrió un problema."))
        if exc.status_code in (400, 403) and isinstance(exc.detail, str) and exc.detail:
            message = exc.detail
        return render_error(request, exc.status_code, title, message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return render_error(request, 400, *ERROR_TITLES[400])

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        # El detalle va al log del contenedor, nunca al navegador
        logger.exception("Error no controlado en %s %s", request.method, request.url.path)
        return render_error(request, 500, "Error interno", "Intenta de nuevo más tarde.")

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    app.include_router(pages.router)
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(teacher.router)
    app.include_router(student.router)
    app.include_router(documents.router)
    return app


app = create_app()
