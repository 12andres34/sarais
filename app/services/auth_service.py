"""Autenticación: contraseña, bloqueo por intentos fallidos y MFA (TOTP).
La criptografía la hace app.security; aquí solo está el flujo."""
import logging
import secrets
from dataclasses import dataclass
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import security
from app.config import get_settings
from app.services.audit_service import AuditAction, record

logger = logging.getLogger("sarais.auth")

# Un solo mensaje para todo fallo: no revela si el usuario existe o está bloqueado
GENERIC_ERROR = "Usuario o contraseña incorrectos, o cuenta bloqueada temporalmente."

# Resultados del segundo factor
MFA_OK = "ok"
MFA_INVALID = "invalid"
MFA_RESTART = "restart"  # bloqueado, inactivo o estado inconsistente: volver a /login

_dummy_hash: str | None = None


def _get_dummy_hash() -> str:
    """Hash falso para gastar el mismo tiempo cuando el usuario no existe."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = security.hash_password(secrets.token_urlsafe(16))
    return _dummy_hash


@dataclass
class SessionUser:
    user_id: int
    username: str
    role: str
    teacher_id: int | None
    student_id: int | None


@dataclass
class PasswordResult:
    ok: bool
    user_id: int | None = None
    mfa_enabled: bool = False


def load_session_user(db: Connection, user_id: int) -> SessionUser | None:
    """Datos del usuario logueado. Se consulta en cada petición: si lo desactivan, pierde acceso."""
    row = db.execute(text("""
        SELECT u.user_id, u.username, r.role_name, t.teacher_id, s.student_id
          FROM users u
          JOIN roles r         ON r.role_id = u.role_id
          LEFT JOIN teachers t ON t.user_id = u.user_id
          LEFT JOIN students s ON s.user_id = u.user_id
         WHERE u.user_id = :uid AND u.is_active = 1
    """), {"uid": user_id}).mappings().first()
    if row is None:
        return None
    return SessionUser(row["user_id"], row["username"], row["role_name"], row["teacher_id"], row["student_id"])


def check_password(db: Connection, username: str, password: str, ip: str | None) -> PasswordResult:
    """Paso 1 del login. Ojo: NO lanzar excepciones aquí, o se pierde
    (ROLLBACK) el contador de intentos fallidos."""
    row = db.execute(text("""
        SELECT user_id, password_hash, mfa_enabled, is_active,
               (locked_until IS NOT NULL AND locked_until > NOW()) AS is_locked
          FROM users
         WHERE username = :username
    """), {"username": username}).mappings().first()

    if row is None:
        security.verify_password(password, _get_dummy_hash())
        record(AuditAction.LOGIN_FAILED, user_id=None, ip=ip, success=False, details={"reason": "unknown_user"})
        return PasswordResult(ok=False)

    if not row["is_active"] or row["is_locked"]:
        reason = "inactive" if not row["is_active"] else "locked"
        record(AuditAction.LOGIN_FAILED, user_id=row["user_id"], ip=ip, success=False, details={"reason": reason})
        return PasswordResult(ok=False)

    if not security.verify_password(password, row["password_hash"]):
        register_failure(db, row["user_id"], ip, AuditAction.LOGIN_FAILED, "bad_password")
        return PasswordResult(ok=False)

    return PasswordResult(ok=True, user_id=row["user_id"], mfa_enabled=bool(row["mfa_enabled"]))


def register_failure(db: Connection, user_id: int, ip: str | None, action: str, reason: str) -> bool:
    """Suma un intento fallido; al llegar al máximo bloquea la cuenta. Devuelve True si quedó bloqueada."""
    s = get_settings()
    current = db.execute(
        text("SELECT failed_attempts FROM users WHERE user_id = :uid FOR UPDATE"), {"uid": user_id}
    ).scalar_one()
    attempts = current + 1
    record(action, user_id=user_id, ip=ip, success=False, details={"reason": reason, "attempt": attempts})

    if attempts >= s.max_failed_attempts:
        # Se reinicia el contador: al terminar el bloqueo hay otros N intentos
        db.execute(text("""
            UPDATE users SET failed_attempts = 0,
                             locked_until = NOW() + INTERVAL :mins MINUTE
             WHERE user_id = :uid
        """), {"mins": s.lock_minutes, "uid": user_id})
        record(AuditAction.ACCOUNT_LOCKED, user_id=user_id, ip=ip, success=False,
               details={"minutes": s.lock_minutes})
        return True

    db.execute(text("UPDATE users SET failed_attempts = :n WHERE user_id = :uid"),
               {"n": attempts, "uid": user_id})
    return False


def register_success(db: Connection, user_id: int) -> None:
    db.execute(text("""
        UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login_at = NOW()
         WHERE user_id = :uid
    """), {"uid": user_id})


def is_mfa_enabled(db: Connection, user_id: int) -> bool:
    value = db.execute(text("SELECT mfa_enabled FROM users WHERE user_id = :uid"),
                       {"uid": user_id}).scalar_one_or_none()
    return bool(value)


def get_or_create_setup_secret(db: Connection, user_id: int) -> tuple[str, str]:
    """Para el primer registro de MFA. Guarda el secreto CIFRADO con mfa_enabled = 0.
    Devuelve (secreto en claro para mostrarlo una vez, username)."""
    row = db.execute(text("""
        SELECT username, mfa_enabled, mfa_secret_encrypted FROM users WHERE user_id = :uid
    """), {"uid": user_id}).mappings().first()
    if row is None or row["mfa_enabled"]:
        raise ValueError("MFA ya está activo o el usuario no existe")
    if row["mfa_secret_encrypted"] is not None:
        return security.decrypt_secret(row["mfa_secret_encrypted"]), row["username"]
    secret = security.generate_totp_secret()
    db.execute(text("""
        UPDATE users SET mfa_secret_encrypted = :enc WHERE user_id = :uid AND mfa_enabled = 0
    """), {"enc": security.encrypt_secret(secret), "uid": user_id})
    return secret, row["username"]


def build_otpauth_uri(secret: str, username: str, issuer: str = "SARAIS") -> str:
    """URI estándar que entienden Google Authenticator, Authy, etc."""
    label = quote(f"{issuer}:{username}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&digits=6&period=30"


def verify_second_factor(db: Connection, user_id: int, code: str, ip: str | None, *, setup: bool) -> str:
    """Paso 2 del login. setup=True cuando el usuario está registrando MFA por primera vez."""
    row = db.execute(text("""
        SELECT is_active, mfa_enabled, mfa_secret_encrypted,
               (locked_until IS NOT NULL AND locked_until > NOW()) AS is_locked
          FROM users WHERE user_id = :uid
    """), {"uid": user_id}).mappings().first()

    if row is None or not row["is_active"] or row["is_locked"]:
        return MFA_RESTART
    # En registro MFA debe estar apagado; en verificación debe estar encendido
    if bool(row["mfa_enabled"]) == setup or row["mfa_secret_encrypted"] is None:
        return MFA_RESTART

    try:
        secret = security.decrypt_secret(row["mfa_secret_encrypted"])
    except Exception:
        logger.exception("No se pudo descifrar el secreto TOTP del usuario %s", user_id)
        return MFA_RESTART

    if not security.verify_totp(secret, code):
        locked = register_failure(db, user_id, ip, AuditAction.MFA_FAILED, "bad_totp")
        return MFA_RESTART if locked else MFA_INVALID

    if setup:
        db.execute(text("UPDATE users SET mfa_enabled = 1 WHERE user_id = :uid"), {"uid": user_id})
        record(AuditAction.MFA_ENABLED, user_id=user_id, ip=ip)
    register_success(db, user_id)
    record(AuditAction.LOGIN_SUCCESS, user_id=user_id, ip=ip)
    return MFA_OK
