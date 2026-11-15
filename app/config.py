"""Configuración de la app leída de variables de entorno (nunca secretos en el código)."""
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

# Colombia no tiene horario de verano: UTC-5 fijo (evita depender de tzdata en la imagen)
LOCAL_TZ = timezone(timedelta(hours=-5))


@dataclass(frozen=True)
class Settings:
    app_env: str                 # development | test | production
    secret_key: str              # firma la cookie de sesión
    mysql_host: str
    mysql_port: int
    mysql_database: str
    mysql_user: str
    mysql_password: str
    mysql_ssl_ca: str | None     # ruta al CA para TLS app->MySQL (opcional)
    mongo_uri: str
    cookie_secure: bool          # cookie solo por HTTPS
    session_idle_minutes: int    # cierre por inactividad
    session_max_age_seconds: int # vida máxima de la cookie
    max_failed_attempts: int     # intentos antes de bloquear
    lock_minutes: int            # duración del bloqueo
    mfa_pending_minutes: int     # tiempo para ingresar el código TOTP

    @property
    def is_production(self) -> bool:
        # Cualquier valor distinto de development/test se trata como producción
        return self.app_env not in ("development", "test")


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def load_settings(environ: dict | None = None) -> Settings:
    env = os.environ if environ is None else environ

    def required(name: str) -> str:
        value = env.get(name, "")
        if not value:
            raise RuntimeError(f"Falta la variable de entorno obligatoria {name}")
        return value

    # Si APP_ENV no está definida se asume producción (lo más estricto)
    app_env = env.get("APP_ENV", "production").strip().lower() or "production"

    secret_key = required("SECRET_KEY")
    if len(secret_key) < 32:
        raise RuntimeError("SECRET_KEY debe tener al menos 32 caracteres")

    cookie_secure = _as_bool(env.get("COOKIE_SECURE"), True)
    if app_env not in ("development", "test") and not cookie_secure:
        raise RuntimeError("COOKIE_SECURE no puede ser false en producción")

    return Settings(
        app_env=app_env,
        secret_key=secret_key,
        mysql_host=env.get("MYSQL_HOST", "mysql_db"),
        mysql_port=int(env.get("MYSQL_PORT", "3306")),
        mysql_database=required("MYSQL_DATABASE"),
        mysql_user=required("MYSQL_USER"),
        mysql_password=required("MYSQL_PASSWORD"),
        mysql_ssl_ca=env.get("MYSQL_SSL_CA") or None,
        mongo_uri=required("MONGO_URI"),
        cookie_secure=cookie_secure,
        session_idle_minutes=int(env.get("SESSION_IDLE_MINUTES", "30")),
        session_max_age_seconds=int(env.get("SESSION_MAX_AGE_SECONDS", str(8 * 3600))),
        max_failed_attempts=int(env.get("MAX_FAILED_ATTEMPTS", "5")),
        lock_minutes=int(env.get("LOCK_MINUTES", "15")),
        mfa_pending_minutes=int(env.get("MFA_PENDING_MINUTES", "5")),
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()


def today_local() -> date:
    """Fecha de hoy en Colombia (el contenedor corre en UTC)."""
    return datetime.now(LOCAL_TZ).date()
