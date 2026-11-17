"""MFA con TOTP (RFC 6238): secreto, verificación anti-reutilización y QR en SVG."""
from __future__ import annotations

import hashlib
import hmac
import io
import threading
import time

import pyotp
import segno

ISSUER = "SARAIS"
TOTP_INTERVAL = 30  # segundos por código
VALID_WINDOW = 1    # acepta el código anterior y el siguiente (±30 s de desfase de reloj)

# Último paso de tiempo (counter) usado por cada secreto.
# Clave: SHA-256 del secreto (no guardamos el secreto en claro en memoria extra).
_last_used: dict[str, tuple[int, float]] = {}
_lock = threading.Lock()


def _now() -> float:
    # Función aparte para poder simular el reloj en las pruebas
    return time.time()


def generate_totp_secret() -> str:
    """Secreto base32 de 32 caracteres (160 bits)."""
    return pyotp.random_base32()


def _purge_expired(now: float) -> None:
    expired = [k for k, (_, exp) in _last_used.items() if exp <= now]
    for k in expired:
        del _last_used[k]


def verify_totp(secret: str, code: str) -> bool:
    """True si el código es válido Y no se ha usado antes.

    Un mismo código (mismo paso de 30 s) solo sirve una vez: si un atacante
    lo ve por encima del hombro, ya no le sirve.
    """
    if not isinstance(secret, str) or not isinstance(code, str):
        return False
    code = code.replace(" ", "").strip()
    if len(code) != 6 or not code.isdigit():
        return False

    now = _now()
    current = int(now // TOTP_INTERVAL)
    matched: int | None = None
    try:
        totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL)
        for offset in range(-VALID_WINDOW, VALID_WINDOW + 1):
            counter = current + offset
            # compare_digest: comparación en tiempo constante
            if hmac.compare_digest(totp.generate_otp(counter), code):
                matched = counter
    except Exception:  # secreto base32 inválido
        return False
    if matched is None:
        return False

    key = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    with _lock:
        _purge_expired(now)
        last = _last_used.get(key)
        if last is not None and matched <= last[0]:
            return False  # código ya usado (o uno más viejo que el último usado)
        # Se guarda hasta que el código deja de ser válido por la ventana
        expires_at = (matched + VALID_WINDOW + 2) * TOTP_INTERVAL
        _last_used[key] = (matched, expires_at)
    return True


def totp_qr_svg(secret: str, username: str) -> str:
    """QR (SVG en línea) con la URI otpauth://. Se genera en el servidor, sin CDN.

    Ojo: el QR contiene el secreto. La página que lo muestre debe enviar
    Cache-Control: no-store.
    """
    uri = pyotp.TOTP(secret, interval=TOTP_INTERVAL).provisioning_uri(
        name=username, issuer_name=ISSUER
    )
    qr = segno.make(uri, error="m", micro=False)
    buff = io.BytesIO()
    qr.save(buff, kind="svg", scale=5, border=2, xmldecl=False, svgns=True,
            dark="#000000", light="#ffffff")
    return buff.getvalue().decode("utf-8")
