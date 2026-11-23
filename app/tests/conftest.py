"""Configuración de pruebas: NO necesita MySQL ni MongoDB (se usan dobles falsos)."""
import os

# Variables de prueba ANTES de importar la app (valores falsos, no son secretos reales)
os.environ.update({
    "APP_ENV": "test",
    "SECRET_KEY": "test-only-secret-key-0123456789-abcdefghij",
    "COOKIE_SECURE": "false",  # TestClient usa http://testserver
    "MYSQL_DATABASE": "test", "MYSQL_USER": "test", "MYSQL_PASSWORD": "test",
    "MONGO_URI": "mongodb://127.0.0.1:1/sarais_test",
    "TOTP_ENC_KEY": "dGVzdC1vbmx5LXRvdHAta2V5LTMyLWJ5dGVzLTAwMDA=",  # 32 bytes en base64 (falsa)
})

import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.services.auth_service import SessionUser  # noqa: E402


class FakeResult:
    """Resultado vacío: simula que la consulta no encontró filas."""
    def mappings(self): return self
    def first(self): return None
    def all(self): return []
    def scalar_one_or_none(self): return None
    def __iter__(self): return iter([])


class FakeDB:
    """Guarda cada SQL y sus parámetros para poder revisarlos en la prueba."""
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        return FakeResult()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def fake_db():
    db = FakeDB()
    app.dependency_overrides[get_db] = lambda: db
    return db


@pytest.fixture
def login_as():
    """Simula un usuario autenticado con cierto rol."""
    def _login(role, teacher_id=None, student_id=None):
        user = SessionUser(user_id=99, username=f"{role}.test", role=role,
                           teacher_id=teacher_id, student_id=student_id)
        app.dependency_overrides[get_current_user] = lambda: user
        return user
    return _login


@pytest.fixture
def audit_calls(monkeypatch):
    """Captura la auditoría en vez de escribir en MongoDB."""
    calls = []
    monkeypatch.setattr("app.services.audit_service.security.audit_log",
                        lambda action, **kw: calls.append((action, kw)))
    return calls


def extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "La página no tiene token CSRF"
    return match.group(1)


@pytest.fixture
def gpg_env(tmp_path, monkeypatch):
    """Keyring GPG temporal con una llave de PRUEBA y carpeta de documentos temporal."""
    if shutil.which("gpg") is None:
        pytest.skip("gpg no instalado")
    home = tmp_path / "gnupg"
    home.mkdir(mode=0o700)
    docs = tmp_path / "documents"
    docs.mkdir()
    monkeypatch.setenv("GNUPGHOME", str(home))
    monkeypatch.setenv("DOCUMENTS_DIR", str(docs))
    subprocess.run(["gpg", "--batch", "--passphrase", "", "--quick-gen-key",
                    "SARAIS Test <test@example.invalid>", "default", "default", "never"],
                   check=True, capture_output=True)
    out = subprocess.run(["gpg", "--batch", "--with-colons", "--list-keys"],
                         check=True, capture_output=True, text=True).stdout
    fpr = next(line.split(":")[9] for line in out.splitlines() if line.startswith("fpr"))
    monkeypatch.setenv("DOCS_GPG_RECIPIENT", fpr)
    yield docs
    subprocess.run(["gpgconf", "--kill", "gpg-agent"], capture_output=True)
