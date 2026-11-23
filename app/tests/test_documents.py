"""Subida de documentos: rol, CSRF, validación del PDF, cifrado GPG, metadatos y auditoría.

Ejecutar desde la raíz del repo:  pytest -v app/tests/test_documents.py
No necesita MySQL ni MongoDB (dobles falsos). La prueba de cifrado usa gpg real
con una llave temporal de prueba (si gpg no está instalado, se salta).
"""
import re
import subprocess
from typing import get_args

import pytest
from pymongo.errors import PyMongoError

from app.models.forms import DocType
from app.security import audit as audit_mod
from app.services import document_service
from app.services.document_service import UploadRejected
from app.tests.conftest import FakeDB, extract_csrf

# PDF mínimo sintético: empieza con %PDF- y termina con %%EOF
PDF = b"%PDF-1.4\n% documento sintetico de prueba\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
UUID_PATH = re.compile(r"^documents/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.gpg$")


# ------------------------------ Dobles falsos ------------------------------
class Rows:
    def __init__(self, rows): self.rows = rows
    def mappings(self): return self
    def all(self): return self.rows
    def first(self): return self.rows[0] if self.rows else None


class StudentDB(FakeDB):
    """Responde a las consultas de estudiantes permitidos y de nombres."""
    def __init__(self, allowed=(1,)):
        super().__init__()
        self.allowed = set(allowed)

    def execute(self, statement, params=None):
        sql, params = str(statement), params or {}
        self.calls.append((sql, params))
        if "WHERE student_id IN" in sql:
            return Rows([{"id": i, "name": f"Apellido{i} Nombre{i}"} for i in params["ids"]])
        if "WHERE user_id IN" in sql:
            return Rows([{"id": i, "name": f"user{i}"} for i in params["ids"]])
        if "FROM students s" in sql or "JOIN students s" in sql:
            sid = params.get("sid")
            ids = sorted(self.allowed) if sid is None else ([sid] if sid in self.allowed else [])
            return Rows([{"student_id": i, "last_name": f"Apellido{i}", "first_name": f"Nombre{i}"} for i in ids])
        return Rows([])


class FakeCursor:
    def __init__(self, docs): self.docs = docs
    def sort(self, *args): return self
    def limit(self, n): self.docs = self.docs[:n]; return self
    def __iter__(self): return iter(self.docs)


class FakeCollection:
    def __init__(self):
        self.docs, self.queries, self.fail = [], [], False

    def insert_one(self, doc):
        if self.fail:
            raise PyMongoError("simulado")
        self.docs.append(dict(doc))

    def find(self, query, projection=None):
        self.queries.append(query)
        return FakeCursor([d for d in self.docs if all(d.get(k) == v for k, v in query.items())])


class FakeMongo:
    def __init__(self): self.cols = {}
    def __getitem__(self, name): return self.cols.setdefault(name, FakeCollection())


@pytest.fixture
def mongo(monkeypatch):
    fake = FakeMongo()
    monkeypatch.setattr("app.routers.documents.get_mongo_db", lambda: fake)
    return fake


@pytest.fixture
def student_db():
    from app.db import get_db
    from app.main import app
    db = StudentDB(allowed=(1, 2))
    app.dependency_overrides[get_db] = lambda: db
    return db


@pytest.fixture
def no_encrypt(monkeypatch):
    """Falla la prueba si alguien intenta cifrar (para casos que deben rechazarse antes)."""
    def _boom(data):
        raise AssertionError("No debía llegar a cifrar")
    monkeypatch.setattr("app.services.document_service.security.encrypt_document", _boom)


def _post(client, token, *, student_id="1", doc_type="MEDICAL_EXCUSE",
          filename="excusa_sintetica.pdf", content=PDF):
    return client.post("/documents", follow_redirects=False,
                       data={"csrf_token": token, "student_id": student_id, "doc_type": doc_type},
                       files={"document": (filename, content, "application/pdf")})


# ------------------------------ Control por rol ------------------------------
def test_anonymous_is_redirected(client):
    response = client.get("/documents", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"


@pytest.mark.parametrize("method", ["get", "post"])
def test_student_cannot_use_documents(client, fake_db, login_as, method):
    login_as("student", student_id=1)
    response = getattr(client, method)("/documents")
    assert response.status_code == 403


def test_teacher_without_teacher_link_is_rejected(client, fake_db, login_as):
    login_as("teacher", teacher_id=None)
    assert client.get("/documents").status_code == 403


def test_admin_and_teacher_see_form(client, student_db, mongo, login_as):
    for role in ("admin", "teacher"):
        login_as(role, teacher_id=5)
        html = client.get("/documents").text
        assert 'enctype="multipart/form-data"' in html
        assert 'name="csrf_token"' in html
        assert "Apellido1 Nombre1" in html


def test_teacher_form_hides_admin_only_types(client, student_db, mongo, login_as):
    login_as("teacher", teacher_id=5)
    html = client.get("/documents").text
    assert "MEDICAL_EXCUSE" in html
    assert "ID_DOCUMENT" not in html and "ENROLLMENT_FORM" not in html


# --------------------------------- CSRF ---------------------------------
def test_upload_without_csrf_is_rejected(client, student_db, mongo, login_as, no_encrypt):
    login_as("admin")
    client.get("/login")  # crea la sesión
    response = _post(client, "token-falso")
    assert response.status_code == 403
    assert "CSRF" in response.text
    assert mongo["document_metadata"].docs == []


def test_upload_requires_multipart(client, student_db, mongo, login_as, no_encrypt):
    login_as("admin")
    token = extract_csrf(client.get("/login").text)
    response = client.post("/documents", data={"csrf_token": token, "student_id": "1"})
    assert response.status_code == 400


# ------------------------------ Validaciones ------------------------------
@pytest.mark.parametrize("filename, content, reason", [
    ("foto.png", PDF, "not_pdf"),                      # extensión
    ("falso.pdf", b"MZ\x90\x00 ejecutable", "not_pdf"),  # firma
    ("vacio.pdf", b"", "empty"),
    ("cortado.pdf", b"%PDF-1.4\n1 0 obj<<>>", "pdf_truncated"),
])
def test_invalid_files_are_rejected_and_audited(client, student_db, mongo, login_as, audit_calls,
                                                no_encrypt, filename, content, reason):
    login_as("admin")
    token = extract_csrf(client.get("/login").text)
    response = _post(client, token, filename=filename, content=content)
    assert response.status_code == 303
    assert mongo["document_metadata"].docs == []
    action, kw = audit_calls[-1]
    assert action == "document_uploaded" and kw["success"] is False
    assert kw["details"]["reason"] == reason


def test_teacher_cannot_upload_for_student_outside_groups(client, student_db, mongo, login_as,
                                                          audit_calls, no_encrypt):
    login_as("teacher", teacher_id=7)
    token = extract_csrf(client.get("/login").text)
    _post(client, token, student_id="999")
    assert audit_calls[-1][1]["details"] == {"reason": "student_not_allowed", "student_id": 999}
    # El filtro usa el teacher_id de la SESIÓN, no uno del formulario
    sql, params = next(c for c in student_db.calls if "teaching_assignments" in c[0])
    assert "ta.teacher_id = :tid" in sql
    assert params == {"tid": 7, "sid": 999}


def test_teacher_cannot_upload_admin_only_type(client, student_db, mongo, login_as,
                                               audit_calls, no_encrypt):
    login_as("teacher", teacher_id=7)
    token = extract_csrf(client.get("/login").text)
    _post(client, token, doc_type="ID_DOCUMENT")
    assert audit_calls[-1][1]["details"]["reason"] == "type_not_allowed"


def test_unknown_doc_type_is_rejected(client, student_db, mongo, login_as, audit_calls, no_encrypt):
    login_as("admin")
    token = extract_csrf(client.get("/login").text)
    _post(client, token, doc_type="SECRETO")
    assert audit_calls[-1][1]["details"]["reason"] == "invalid_form"


def test_too_large_is_rejected_before_reading(client, student_db, mongo, login_as, audit_calls,
                                              no_encrypt, monkeypatch):
    monkeypatch.setattr("app.routers.documents.MAX_DOCUMENT_BYTES", 10)
    monkeypatch.setattr("app.routers.documents.FORM_OVERHEAD", 0)
    login_as("admin")
    token = extract_csrf(client.get("/login").text)
    response = _post(client, token)
    assert response.status_code == 413
    assert audit_calls[-1][1]["details"]["reason"] == "too_large"


def test_validate_pdf_size_limit(monkeypatch):
    monkeypatch.setattr(document_service, "MAX_DOCUMENT_BYTES", len(PDF) - 1)
    with pytest.raises(UploadRejected) as exc:
        document_service.validate_pdf(PDF, "a.pdf")
    assert exc.value.reason == "too_large"


# --------------------- Camino feliz: GPG real + metadatos ---------------------
def test_upload_encrypts_and_stores_only_ids(client, student_db, mongo, login_as, audit_calls, gpg_env):
    login_as("admin")
    token = extract_csrf(client.get("/login").text)
    response = _post(client, token, student_id="2", doc_type="ID_DOCUMENT",
                     filename="cedula_Juana_Perez.pdf")
    assert response.status_code == 303

    # 1) Metadatos: exactamente los campos del validador de Mongo, sin nombre de archivo
    [meta] = mongo["document_metadata"].docs
    assert set(meta) == {"type", "upload_date", "uploader_id", "student_ref", "storage_path"}
    assert meta["type"] == "ID_DOCUMENT" and meta["student_ref"] == 2 and meta["uploader_id"] == 99
    assert UUID_PATH.match(meta["storage_path"])
    assert "Juana" not in str(meta)

    # 2) Archivo cifrado: no contiene el PDF en claro y se descifra con la llave privada de prueba
    gpg_file = gpg_env / meta["storage_path"].split("/", 1)[1]
    raw = gpg_file.read_bytes()
    assert b"%PDF" not in raw
    plain = subprocess.run(["gpg", "--batch", "--quiet", "--decrypt", str(gpg_file)],
                           check=True, capture_output=True).stdout
    assert plain == PDF

    # 3) Auditoría: éxito, solo IDs y códigos, y pasa el filtro de audit.py sin descartar nada
    action, kw = audit_calls[-1]
    assert action == "document_uploaded" and kw["success"] is True and kw["user_id"] == 99
    assert kw["details"] == {"student_id": 2, "doc_type": "ID_DOCUMENT",
                             "storage_path": meta["storage_path"], "size_bytes": len(PDF)}
    assert "dropped_keys" not in audit_mod._clean_details(kw["details"])


def test_mongo_failure_removes_encrypted_file(client, student_db, mongo, login_as, audit_calls, gpg_env):
    mongo["document_metadata"].fail = True
    login_as("admin")
    token = extract_csrf(client.get("/login").text)
    response = _post(client, token)
    assert response.status_code == 303
    assert list(gpg_env.iterdir()) == []  # no quedan .gpg huérfanos
    assert audit_calls[-1][1]["details"]["reason"] == "storage_error"


def test_missing_gpg_key_is_handled(client, student_db, mongo, login_as, audit_calls, monkeypatch, tmp_path):
    monkeypatch.setenv("DOCS_GPG_RECIPIENT", "")
    monkeypatch.setenv("DOCUMENTS_DIR", str(tmp_path))
    login_as("admin")
    token = extract_csrf(client.get("/login").text)
    response = _post(client, token)
    assert response.status_code == 303  # aviso al usuario, no error 500
    assert audit_calls[-1][1]["details"]["reason"] == "storage_error"


# ---------------------------------- Lista ----------------------------------
def test_teacher_list_shows_only_own_uploads(client, student_db, mongo, login_as):
    col = mongo["document_metadata"]
    col.docs = [
        {"type": "OTHER", "uploader_id": 99, "student_ref": 1, "storage_path": "documents/mio.gpg"},
        {"type": "OTHER", "uploader_id": 50, "student_ref": 2, "storage_path": "documents/ajeno.gpg"},
    ]
    login_as("teacher", teacher_id=7)
    html = client.get("/documents").text
    assert col.queries[-1] == {"uploader_id": 99}
    assert "documents/mio.gpg" in html and "documents/ajeno.gpg" not in html


def test_admin_list_shows_all(client, student_db, mongo, login_as):
    col = mongo["document_metadata"]
    col.docs = [{"type": "OTHER", "uploader_id": 50, "student_ref": 2, "storage_path": "documents/x.gpg"}]
    login_as("admin")
    html = client.get("/documents").text
    assert col.queries[-1] == {}
    assert "documents/x.gpg" in html and "Apellido2 Nombre2" in html and "user50" in html


# ------------------------------ Coherencia ------------------------------
def test_doc_types_match_form_and_mongo_validator():
    from pathlib import Path
    assert set(document_service.DOC_TYPES) == set(get_args(DocType))
    init_js = (Path(__file__).resolve().parents[2] / "db/mongo/init/01_init_mongo.js").read_text()
    for code in document_service.DOC_TYPES:
        assert f"'{code}'" in init_js
