"""
=====================================================================
  ⚠️  STUB TEMPORAL — NO ES EL MÓDULO DE SEGURIDAD DEFINITIVO  ⚠️
---------------------------------------------------------------------
  Este archivo lo REEMPLAZA el chat de seguridad (carpeta app/security/).
  Solo existe para que la app funcione en desarrollo mientras tanto.

  Contrato que el módulo definitivo DEBE respetar (mismas firmas):
    hash_password(password: str) -> str
    verify_password(password: str, password_hash: str) -> bool   # False ante hash inválido, nunca excepción
    generate_totp_secret() -> str                                 # base32
    verify_totp(secret: str, code: str) -> bool
    encrypt_secret(plain: str) -> bytes                           # cabe en VARBINARY(512)
    decrypt_secret(token: bytes) -> str
    audit_log(action: str, *, user_id: int | None, ip: str | None,
              success: bool, details: dict | None = None) -> None

  Protección: con IS_STUB = True la app NO arranca si APP_ENV=production
  (ver app/main.py). El módulo definitivo no debe definir IS_STUB.
=====================================================================
"""
import base64
import hashlib
import logging
import os
from datetime import datetime, timezone

import pyotp
from argon2 import PasswordHasher
from cryptography.fernet import Fernet

IS_STUB = True
logger = logging.getLogger("sarais.security.stub")
_hasher = PasswordHasher()  # STUB: parámetros por defecto de argon2-cffi


def hash_password(password: str) -> str:  # STUB
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:  # STUB
    try:
        return _hasher.verify(password_hash, password)
    except Exception:  # hash inválido, placeholder o contraseña incorrecta
        return False


def generate_totp_secret() -> str:  # STUB
    return pyotp.random_base32()


def verify_totp(secret: str, code: str) -> bool:  # STUB (no evita reutilizar un código)
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def _fernet() -> Fernet:  # STUB: deriva una llave Fernet de TOTP_ENC_KEY
    key = os.environ.get("TOTP_ENC_KEY", "")
    if not key:
        raise RuntimeError("Falta la variable de entorno TOTP_ENC_KEY")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))


def encrypt_secret(plain: str) -> bytes:  # STUB
    return _fernet().encrypt(plain.encode())


def decrypt_secret(token: bytes) -> str:  # STUB
    return _fernet().decrypt(bytes(token)).decode()


def audit_log(action: str, *, user_id: int | None, ip: str | None,
              success: bool, details: dict | None = None) -> None:  # STUB
    doc = {
        "timestamp": datetime.now(timezone.utc),
        "user_id": user_id,
        "action": action,
        "ip": ip,
        "result": "success" if success else "failure",
        "details": details or {},
    }
    try:
        from app.db import get_mongo_db  # import tardío: evita ciclos
        get_mongo_db()["audit_logs"].insert_one(doc)
    except Exception as exc:  # el validador real puede rechazar este formato
        logger.warning("STUB audit_log no pudo escribir (%s): %s", type(exc).__name__, doc)
