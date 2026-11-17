"""Hash y verificación de contraseñas con Argon2id."""
from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError

# Parámetros del perfil "low memory" de RFC 9106: 3 pasadas, 64 MiB, 4 hilos.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # KiB = 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

MAX_PASSWORD_LENGTH = 1024  # evita DoS con contraseñas gigantes


def hash_password(password: str) -> str:
    """Devuelve un hash Argon2id en formato PHC ($argon2id$v=19$...)."""
    if not isinstance(password, str) or not password:
        raise ValueError("La contraseña no puede estar vacía")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError("Contraseña demasiado larga")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """True si coincide. False ante error o hash inválido; nunca lanza excepción."""
    try:
        if not isinstance(password, str) or not isinstance(password_hash, str):
            return False
        if not password or len(password) > MAX_PASSWORD_LENGTH:
            return False
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:  # hash corrupto, placeholder, tipo raro, etc.
        return False

