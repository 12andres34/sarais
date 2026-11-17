"""Módulo de seguridad de SARAIS (reemplaza al STUB; no define IS_STUB).

La app lo usa como:  from app import security  ->  security.hash_password(...)
"""
from .audit import AUDIT_ACTIONS, audit_log
from .crypto import decrypt_secret, encrypt_document, encrypt_secret
from .passwords import hash_password, verify_password
from .totp import generate_totp_secret, totp_qr_svg, verify_totp

__all__ = [
    "AUDIT_ACTIONS",
    "audit_log",
    "decrypt_secret",
    "encrypt_document",
    "encrypt_secret",
    "generate_totp_secret",
    "hash_password",
    "totp_qr_svg",
    "verify_password",
    "verify_totp",
]
