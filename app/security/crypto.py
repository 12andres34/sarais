"""Cifrado: secreto MFA con AES-256-GCM y documentos con GPG (llave pública)."""
from __future__ import annotations

import base64
import binascii
import os
import re
import secrets
import subprocess
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ---------- Secreto MFA (AES-256-GCM) ----------
# Formato del token: versión (1 byte) | nonce (12 bytes) | texto cifrado + tag (16 bytes)
_TOKEN_VERSION = b"\x01"
_NONCE_LEN = 12
_TAG_LEN = 16
_AAD = b"sarais:totp-secret:v1"  # dato asociado: liga el token a este uso
MAX_TOKEN_LEN = 512               # columna users.totp_secret_enc VARBINARY(512)


def _load_key() -> bytes:
    """Lee TOTP_ENC_KEY: 32 bytes en base64 (estándar o urlsafe) o 64 caracteres hex."""
    raw = os.environ.get("TOTP_ENC_KEY", "").strip()
    if not raw:
        raise RuntimeError("TOTP_ENC_KEY no está definida")
    if re.fullmatch(r"[0-9a-fA-F]{64}", raw):
        key = bytes.fromhex(raw)
    else:
        try:
            key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        except (binascii.Error, ValueError):
            raise RuntimeError("TOTP_ENC_KEY no es base64 válido") from None
    if len(key) != 32:
        raise RuntimeError("TOTP_ENC_KEY debe tener 32 bytes (AES-256)")
    return key


def encrypt_secret(plain: str) -> bytes:
    """Cifra el secreto TOTP. Devuelve bytes para guardar en VARBINARY(512)."""
    if not isinstance(plain, str) or not plain:
        raise ValueError("Secreto vacío")
    nonce = secrets.token_bytes(_NONCE_LEN)  # nonce nuevo en cada cifrado
    ciphertext = AESGCM(_load_key()).encrypt(nonce, plain.encode("utf-8"), _AAD)
    token = _TOKEN_VERSION + nonce + ciphertext
    if len(token) > MAX_TOKEN_LEN:
        raise ValueError("Secreto demasiado largo para VARBINARY(512)")
    return token


def decrypt_secret(token: bytes) -> str:
    """Descifra. Lanza ValueError si el token es inválido, fue alterado o la llave cambió."""
    if isinstance(token, (bytearray, memoryview)):
        token = bytes(token)
    if not isinstance(token, bytes) or len(token) < 1 + _NONCE_LEN + _TAG_LEN:
        raise ValueError("Token inválido")
    if token[:1] != _TOKEN_VERSION:
        raise ValueError("Versión de token desconocida (¿formato anterior? reinicia MFA)")
    nonce = token[1:1 + _NONCE_LEN]
    ciphertext = token[1 + _NONCE_LEN:]
    try:
        plain = AESGCM(_load_key()).decrypt(nonce, ciphertext, _AAD)
    except InvalidTag:
        raise ValueError("No se pudo descifrar: llave distinta o dato alterado") from None
    return plain.decode("utf-8")


# ---------- Documentos (GPG) ----------
MAX_DOCUMENT_BYTES = int(os.environ.get("MAX_DOCUMENT_BYTES", str(10 * 1024 * 1024)))


def encrypt_document(data: bytes) -> str:
    """Cifra con la llave pública DOCS_GPG_RECIPIENT y guarda DOCUMENTS_DIR/<uuid>.gpg.

    Devuelve el storage_path relativo: "documents/<uuid>.gpg".
    La app solo tiene la llave PÚBLICA: puede cifrar, pero no descifrar.
    """
    if isinstance(data, (bytearray, memoryview)):
        data = bytes(data)
    if not isinstance(data, bytes) or not data:
        raise ValueError("Documento vacío")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise ValueError("Documento demasiado grande")

    recipient = os.environ.get("DOCS_GPG_RECIPIENT", "").strip()
    if not recipient:
        raise RuntimeError("DOCS_GPG_RECIPIENT no está definida")
    docs_dir = Path(os.environ.get("DOCUMENTS_DIR", "/srv/data/documents"))
    if not docs_dir.is_dir():
        raise RuntimeError(f"DOCUMENTS_DIR no existe: {docs_dir}")

    # --trust-model always: la llave se fija por huella (fingerprint) en DOCS_GPG_RECIPIENT
    # --auto-key-locate clear,local: solo el llavero local. Sin esto, si falta la llave,
    # gpg la busca en Internet (WKD) y revela el destinatario.
    cmd = [
        "gpg", "--batch", "--no-tty", "--quiet", "--yes",
        "--trust-model", "always",
        "--auto-key-locate", "clear,local",
        "--recipient", recipient,
        "--encrypt", "--output", "-",
    ]
    try:
        proc = subprocess.run(cmd, input=data, capture_output=True, timeout=60, check=False)
    except FileNotFoundError:
        raise RuntimeError("gpg no está instalado") from None
    if proc.returncode != 0 or not proc.stdout:
        err = proc.stderr.decode("utf-8", "replace")[:300]
        raise RuntimeError(f"gpg falló al cifrar: {err}")

    name = f"{uuid.uuid4()}.gpg"
    final_path = docs_dir / name
    # O_EXCL: nunca sobrescribe; 0o600: solo el dueño (usuario sarais) puede leer
    fd = os.open(final_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(proc.stdout)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        final_path.unlink(missing_ok=True)
        raise
    return f"documents/{name}"
