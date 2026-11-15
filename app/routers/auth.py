"""Login en dos pasos: contraseña -> código TOTP (o registro de MFA la primera vez)."""
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.engine import Connection

from app.config import get_settings
from app.db import get_db
from app.models.forms import LoginForm, MfaCodeForm
from app.services import auth_service
from app.services.audit_service import AuditAction, record
from app.web import client_ip, flash, read_form, render, validate

router = APIRouter()

PENDING_KEY = "pending_user_id"   # usuario que pasó la contraseña pero no el TOTP
PENDING_SINCE = "pending_since"


def _pending_user_id(request: Request) -> int | None:
    uid = request.session.get(PENDING_KEY)
    since = int(request.session.get(PENDING_SINCE, 0))
    if uid and time.time() - since <= get_settings().mfa_pending_minutes * 60:
        return int(uid)
    request.session.pop(PENDING_KEY, None)
    request.session.pop(PENDING_SINCE, None)
    return None


def _finish_login(request: Request, user_id: int) -> RedirectResponse:
    # Sesión nueva tras autenticarse (evita fijación de sesión)
    request.session.clear()
    request.session["user_id"] = user_id
    request.session["last_seen"] = int(time.time())
    return RedirectResponse("/", status_code=303)


def _restart(request: Request) -> RedirectResponse:
    request.session.clear()
    flash(request, auth_service.GENERIC_ERROR, "error")
    return RedirectResponse("/login", status_code=303)


# ---------------------------- Paso 1 ----------------------------
@router.get("/login")
def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return render(request, "login.html")


@router.post("/login")
async def login_submit(request: Request, db: Connection = Depends(get_db)):
    data = await read_form(request)
    form, error = validate(LoginForm, data)
    if error:
        return render(request, "login.html", {"error": auth_service.GENERIC_ERROR}, status_code=400)

    result = auth_service.check_password(db, form.username, form.password, client_ip(request))
    if not result.ok:
        return render(request, "login.html",
                      {"error": auth_service.GENERIC_ERROR, "username": form.username}, status_code=401)

    request.session.clear()
    request.session[PENDING_KEY] = result.user_id
    request.session[PENDING_SINCE] = int(time.time())
    return RedirectResponse("/login/mfa" if result.mfa_enabled else "/login/mfa/setup", status_code=303)


# ------------------------ Paso 2: verificar ------------------------
@router.get("/login/mfa")
def mfa_page(request: Request, db: Connection = Depends(get_db)):
    uid = _pending_user_id(request)
    if uid is None:
        return RedirectResponse("/login", status_code=303)
    if not auth_service.is_mfa_enabled(db, uid):
        return RedirectResponse("/login/mfa/setup", status_code=303)
    return render(request, "mfa_verify.html")


@router.post("/login/mfa")
async def mfa_submit(request: Request, db: Connection = Depends(get_db)):
    data = await read_form(request)
    uid = _pending_user_id(request)
    if uid is None:
        flash(request, "El tiempo para ingresar el código expiró. Inicia sesión de nuevo.", "error")
        return RedirectResponse("/login", status_code=303)

    form, error = validate(MfaCodeForm, data)
    if error:
        return render(request, "mfa_verify.html", {"error": "El código debe tener 6 dígitos."}, status_code=400)

    status = auth_service.verify_second_factor(db, uid, form.code, client_ip(request), setup=False)
    if status == auth_service.MFA_OK:
        return _finish_login(request, uid)
    if status == auth_service.MFA_RESTART:
        return _restart(request)
    return render(request, "mfa_verify.html", {"error": "Código incorrecto."}, status_code=401)


# ------------------ Paso 2 (primera vez): registrar MFA ------------------
@router.get("/login/mfa/setup")
def mfa_setup_page(request: Request, db: Connection = Depends(get_db)):
    uid = _pending_user_id(request)
    if uid is None:
        return RedirectResponse("/login", status_code=303)
    # Si ya tiene MFA, NO se permite registrar otro (evita saltarse el segundo factor)
    if auth_service.is_mfa_enabled(db, uid):
        return RedirectResponse("/login/mfa", status_code=303)
    secret, username = auth_service.get_or_create_setup_secret(db, uid)
    return render(request, "mfa_setup.html", {
        "secret_groups": [secret[i:i + 4] for i in range(0, len(secret), 4)],
        "otpauth_uri": auth_service.build_otpauth_uri(secret, username),
    })


@router.post("/login/mfa/setup")
async def mfa_setup_submit(request: Request, db: Connection = Depends(get_db)):
    data = await read_form(request)
    uid = _pending_user_id(request)
    if uid is None:
        flash(request, "El tiempo para registrar MFA expiró. Inicia sesión de nuevo.", "error")
        return RedirectResponse("/login", status_code=303)

    form, error = validate(MfaCodeForm, data)
    if error:
        flash(request, "El código debe tener 6 dígitos.", "error")
        return RedirectResponse("/login/mfa/setup", status_code=303)

    status = auth_service.verify_second_factor(db, uid, form.code, client_ip(request), setup=True)
    if status == auth_service.MFA_OK:
        return _finish_login(request, uid)
    if status == auth_service.MFA_RESTART:
        return _restart(request)
    flash(request, "Código incorrecto. Revisa la hora de tu celular e intenta de nuevo.", "error")
    return RedirectResponse("/login/mfa/setup", status_code=303)


# ---------------------------- Salir ----------------------------
@router.post("/logout")
async def logout(request: Request):
    await read_form(request)  # también protegido con CSRF
    user_id = request.session.get("user_id")
    if user_id:
        record(AuditAction.LOGOUT, user_id=int(user_id), ip=client_ip(request))
    request.session.clear()
    flash(request, "Sesión cerrada.", "info")
    return RedirectResponse("/login", status_code=303)
