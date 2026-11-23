"""Pruebas del módulo app/security.

Ejecutar desde la raíz del repo:  pytest -v app/tests/test_security.py
"""
import base64
import os
import re
import secrets
import stat
import subprocess

import pytest

from app.security import (
    AUDIT_ACTIONS, audit_log, decrypt_secret, encrypt_document, encrypt_secret,
    generate_totp_secret, hash_password, totp_qr_svg, verify_password, verify_totp,
)
from app.security import audit as audit_mod
from app.security import totp as totp_mod


@pytest.fixture(autouse=True)
def enc_key(monkeypatch):
    # Llave de prueba generada al vuelo (nunca una real)
    monkeypatch.setenv("TOTP_ENC_KEY", base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())


@pytest.fixture(autouse=True)
def reset_totp_cache():
    totp_mod._last_used.clear()
    yield
    totp_mod._last_used.clear()


# ---------------- Argon2id ----------------
def test_hash_is_argon2id_and_salted():
    h1, h2 = hash_password("Clave-Sintetica-1"), hash_password("Clave-Sintetica-1")
    assert h1.startswith("$argon2id$")
    assert h1 != h2  # sal aleatoria


def test_verify_password_ok_and_wrong():
    h = hash_password("Clave-Sintetica-1")
    assert verify_password("Clave-Sintetica-1", h) is True
    assert verify_password("clave-sintetica-1", h) is False


@pytest.mark.parametrize("bad_hash", ["", "abc", "ARGON2_HASH_PLACEHOLDER",
                                      "$argon2id$v=19$m=1,t=1,p=1$xx$yy", None, 123])
def test_verify_password_invalid_hash_never_raises(bad_hash):
    assert verify_password("x", bad_hash) is False


def test_hash_password_rejects_empty():
    with pytest.raises(ValueError):
        hash_password("")


# ---------------- TOTP ----------------
def _code(secret, t):
    import pyotp
    return pyotp.TOTP(secret).at(t)


def test_secret_is_base32_160_bits():
    s = generate_totp_secret()
    assert len(s) == 32 and re.fullmatch(r"[A-Z2-7]+", s)
    assert len(base64.b32decode(s)) == 20


def test_totp_valid_once_then_replay_rejected(monkeypatch):
    s = generate_totp_secret()
    t = 1_800_000_000.0
    monkeypatch.setattr(totp_mod, "_now", lambda: t)
    code = _code(s, t)
    assert verify_totp(s, code) is True
    assert verify_totp(s, code) is False  # reutilización bloqueada


def test_totp_older_code_rejected_after_newer_used(monkeypatch):
    s = generate_totp_secret()
    t = 1_800_000_000.0
    monkeypatch.setattr(totp_mod, "_now", lambda: t)
    assert verify_totp(s, _code(s, t)) is True
    assert verify_totp(s, _code(s, t - 30)) is False  # código anterior ya no sirve


def test_totp_next_step_accepted(monkeypatch):
    s = generate_totp_secret()
    t = 1_800_000_000.0
    monkeypatch.setattr(totp_mod, "_now", lambda: t)
    assert verify_totp(s, _code(s, t)) is True
    monkeypatch.setattr(totp_mod, "_now", lambda: t + 30)
    assert verify_totp(s, _code(s, t + 30)) is True


def test_totp_window_and_expired(monkeypatch):
    s = generate_totp_secret()
    t = 1_800_000_000.0
    monkeypatch.setattr(totp_mod, "_now", lambda: t)
    assert verify_totp(s, _code(s, t - 30)) is True   # dentro de la ventana
    assert verify_totp(s, _code(s, t - 120)) is False  # demasiado viejo


@pytest.mark.parametrize("code", ["", "12345", "1234567", "abcdef", None])
def test_totp_bad_format(code):
    assert verify_totp(generate_totp_secret(), code) is False


def test_totp_invalid_secret():
    assert verify_totp("no-es-base32!!", "123456") is False


def test_totp_codes_with_spaces(monkeypatch):
    s = generate_totp_secret()
    t = 1_800_000_000.0
    monkeypatch.setattr(totp_mod, "_now", lambda: t)
    c = _code(s, t)
    assert verify_totp(s, f"{c[:3]} {c[3:]}") is True


def test_qr_svg_is_inline_and_offline():
    s = generate_totp_secret()
    svg = totp_qr_svg(s, "docente.demo")
    assert svg.lstrip().startswith("<svg")
    assert "<script" not in svg.lower()
    assert "http://" not in svg.replace("http://www.w3.org", "")  # sin recursos externos
    assert s not in svg  # el secreto no aparece como texto


# ---------------- AES-GCM ----------------
def test_encrypt_decrypt_roundtrip():
    s = generate_totp_secret()
    token = encrypt_secret(s)
    assert isinstance(token, bytes) and len(token) <= 512
    assert s.encode() not in token
    assert decrypt_secret(token) == s


def test_encrypt_uses_random_nonce():
    assert encrypt_secret("ABC") != encrypt_secret("ABC")


def test_tampered_token_rejected():
    token = bytearray(encrypt_secret("ABCDEF"))
    token[-1] ^= 0x01
    with pytest.raises(ValueError):
        decrypt_secret(bytes(token))


def test_wrong_key_rejected(monkeypatch):
    token = encrypt_secret("ABCDEF")
    monkeypatch.setenv("TOTP_ENC_KEY", base64.b64encode(secrets.token_bytes(32)).decode())
    with pytest.raises(ValueError):
        decrypt_secret(token)


def test_old_format_rejected():
    with pytest.raises(ValueError):
        decrypt_secret(b"gAAAAA" + b"x" * 60)  # p. ej. un token Fernet del stub


def test_missing_or_short_key(monkeypatch):
    monkeypatch.delenv("TOTP_ENC_KEY")
    with pytest.raises(RuntimeError):
        encrypt_secret("X")
    monkeypatch.setenv("TOTP_ENC_KEY", base64.b64encode(b"corta").decode())
    with pytest.raises(RuntimeError):
        encrypt_secret("X")


def test_hex_key_accepted(monkeypatch):
    monkeypatch.setenv("TOTP_ENC_KEY", secrets.token_hex(32))
    assert decrypt_secret(encrypt_secret("ABC")) == "ABC"


# ---------------- GPG ----------------
# El fixture gpg_env está en conftest.py (lo usa también test_documents.py)


def test_encrypt_document(gpg_env):
    data = b"%PDF-1.4 documento sintetico de prueba"
    path = encrypt_document(data)
    assert re.fullmatch(r"documents/[0-9a-f-]{36}\.gpg", path)
    f = gpg_env / path.split("/", 1)[1]
    raw = f.read_bytes()
    assert data not in raw
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    # En la prueba sí tenemos la llave privada: comprobamos que descifra igual
    dec = subprocess.run(["gpg", "--batch", "--quiet", "--decrypt", str(f)],
                         check=True, capture_output=True).stdout
    assert dec == data


def test_encrypt_document_unique_names(gpg_env):
    assert encrypt_document(b"a") != encrypt_document(b"a")


def test_encrypt_document_never_looks_up_keys_online(gpg_env, monkeypatch):
    # Llave inexistente: debe fallar con "No public key", sin intentar WKD (Internet)
    monkeypatch.setenv("LC_ALL", "C")  # mensajes de gpg en inglés aunque WSL esté en español
    monkeypatch.setenv("DOCS_GPG_RECIPIENT", "no-existe@example.invalid")
    with pytest.raises(RuntimeError) as exc:
        encrypt_document(b"%PDF-1.4 x")
    assert "No public key" in str(exc.value)
    assert "WKD" not in str(exc.value)
    assert list(gpg_env.iterdir()) == []


def test_encrypt_document_empty_rejected(gpg_env):
    with pytest.raises(ValueError):
        encrypt_document(b"")


# ---------------- Auditoría ----------------
class FakeCollection:
    def __init__(self, fail=False):
        self.docs, self.fail = [], fail

    def insert_one(self, doc):
        if self.fail:
            raise RuntimeError("mongo caído")
        self.docs.append(doc)


def test_audit_log_document_shape(monkeypatch):
    col = FakeCollection()
    monkeypatch.setattr(audit_mod, "_get_collection", lambda: col)
    audit_log("grade_change", user_id=7, ip="172.18.0.5", success=True,
              details={"grade_id": 10, "student_id": 3, "comment": "Juan sacó 2.0"})
    d = col.docs[0]
    assert set(d) == {"timestamp", "user_id", "action", "ip", "result", "details"}
    assert d["result"] == "success" and d["user_id"] == 7
    assert d["details"] == {"grade_id": 10, "student_id": 3, "dropped_keys": 1}
    assert d["timestamp"].tzinfo is not None


def test_audit_log_failure_and_null_user(monkeypatch):
    col = FakeCollection()
    monkeypatch.setattr(audit_mod, "_get_collection", lambda: col)
    audit_log("login_failed", user_id=None, ip="no-ip", success=False,
              details={"reason": "bad_password"})
    d = col.docs[0]
    assert d["user_id"] is None and d["ip"] is None and d["result"] == "failure"
    assert d["details"] == {"reason": "bad_password"}


def test_audit_unknown_action_not_inserted(monkeypatch, caplog):
    col = FakeCollection()
    monkeypatch.setattr(audit_mod, "_get_collection", lambda: col)
    audit_log("delete_everything", user_id=1, ip=None, success=True)
    assert col.docs == [] and "AUDIT_INVALID_ACTION" in caplog.text


def test_audit_never_raises_when_mongo_down(monkeypatch, caplog):
    monkeypatch.setattr(audit_mod, "_get_collection", lambda: FakeCollection(fail=True))
    audit_log("logout", user_id=1, ip="127.0.0.1", success=True)
    assert "AUDIT_FALLBACK" in caplog.text


def test_audit_real_app_details(monkeypatch):
    """Los details que envía hoy la app (teacher_service, admin, auth_service) pasan completos."""
    col = FakeCollection()
    monkeypatch.setattr(audit_mod, "_get_collection", lambda: col)
    grade = {"enrollment_id": 5, "assignment_id": 2, "period_id": 1, "old_score": None, "new_score": 4.5}
    audit_log("grade_change", user_id=7, ip="10.0.0.1", success=True, details=grade)
    att = {"assignment_id": 2, "class_date": "2026-11-17", "records": 20}
    audit_log("attendance_recorded", user_id=7, ip="10.0.0.1", success=True, details=att)
    usr = {"target_user_id": 4, "change": "mfa_reset"}
    audit_log("mfa_reset", user_id=1, ip="10.0.0.1", success=True, details=usr)
    assert [d["details"] for d in col.docs] == [grade, att, usr]


def test_audit_actions_list():
    assert len(AUDIT_ACTIONS) == 14


def test_audit_actions_match_app():
    pytest.importorskip("pymongo")
    from app.services.audit_service import AuditAction
    assert set(AuditAction.ALL) == AUDIT_ACTIONS


@pytest.mark.skipif(os.environ.get("SARAIS_IT_MONGO") != "1",
                    reason="Integración: exporta SARAIS_IT_MONGO=1 y MONGO_URI")
def test_audit_log_real_mongo():
    audit_log("logout", user_id=1, ip="127.0.0.1", success=True, details={"session_id": 1})
    col = audit_mod._get_collection()
    assert col.find_one({"action": "logout", "details.session_id": 1}) is not None
