"""Documentos: validar el PDF, cifrarlo con GPG, guardar metadatos en MongoDB y listarlos.

Reglas:
- En MongoDB solo van IDs y códigos (document_metadata). Nunca el nombre original
  del archivo: puede traer datos personales ("excusa_juan_perez.pdf").
- La app solo tiene la llave PÚBLICA: cifra, pero no puede abrir los documentos.
- El docente solo puede subir documentos de estudiantes de SUS grupos (lo decide el servidor).
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from pymongo.database import Database
from pymongo.errors import PyMongoError
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from app import security
from app.config import LOCAL_TZ
from app.security.crypto import MAX_DOCUMENT_BYTES
from app.services.auth_service import SessionUser
from app.services.errors import ServiceError

logger = logging.getLogger("sarais.documents")

# Mismos valores que el enum "type" del validador (db/mongo/init/01_init_mongo.js)
DOC_TYPES = {
    "ENROLLMENT_FORM": "Formulario de matrícula",
    "REPORT_CARD": "Boletín",
    "ID_DOCUMENT": "Documento de identidad",
    "MEDICAL_EXCUSE": "Excusa médica",
    "OTHER": "Otro",
}
# Control por rol: el docente no maneja documentos de identidad ni de matrícula
ROLE_DOC_TYPES = {
    "admin": list(DOC_TYPES),
    "teacher": ["MEDICAL_EXCUSE", "REPORT_CARD", "OTHER"],
}

PDF_MAGIC = b"%PDF-"   # todo PDF empieza así
PDF_EOF = b"%%EOF"     # y termina con esta marca (en el último KB)
LIST_LIMIT = 100       # documentos que muestra la lista
_STORAGE_RE = re.compile(r"^documents/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.gpg$")


class UploadRejected(ServiceError):
    """Subida rechazada. 'reason' es un código corto que va a la auditoría."""
    def __init__(self, message: str, reason: str):
        super().__init__(message)
        self.reason = reason


def max_mb() -> int:
    return MAX_DOCUMENT_BYTES // (1024 * 1024)


def allowed_types(role: str) -> list[tuple[str, str]]:
    """[(código, etiqueta)] que puede subir este rol."""
    return [(code, DOC_TYPES[code]) for code in ROLE_DOC_TYPES.get(role, [])]


# ------------------------- Estudiantes permitidos -------------------------
# Un solo SQL por rol. ":sid IS NULL" = todos; con un número = solo ese estudiante.
_ADMIN_STUDENTS = text("""
    SELECT s.student_id, s.last_name, s.first_name
      FROM students s
     WHERE s.status = 'active'
       AND (:sid IS NULL OR s.student_id = :sid)
     ORDER BY s.last_name, s.first_name
""")

_TEACHER_STUDENTS = text("""
    SELECT DISTINCT s.student_id, s.last_name, s.first_name
      FROM teaching_assignments ta
      JOIN enrollments e ON e.class_group_id = ta.class_group_id AND e.status = 'active'
      JOIN students s    ON s.student_id = e.student_id AND s.status = 'active'
     WHERE ta.teacher_id = :tid
       AND (:sid IS NULL OR s.student_id = :sid)
     ORDER BY s.last_name, s.first_name
""")


def _students(db: Connection, user: SessionUser, student_id: int | None) -> list[dict]:
    if user.role == "admin":
        rows = db.execute(_ADMIN_STUDENTS, {"sid": student_id})
    elif user.role == "teacher" and user.teacher_id is not None:
        # teacher_id viene de la SESIÓN, nunca del formulario
        rows = db.execute(_TEACHER_STUDENTS, {"tid": user.teacher_id, "sid": student_id})
    else:
        return []
    return [dict(r) for r in rows.mappings().all()]


def list_uploadable_students(db: Connection, user: SessionUser) -> list[dict]:
    return _students(db, user, None)


def ensure_student_allowed(db: Connection, user: SessionUser, student_id: int) -> None:
    if not _students(db, user, student_id):
        raise UploadRejected("El estudiante no existe o no está en tus grupos.", "student_not_allowed")


def ensure_type_allowed(role: str, doc_type: str) -> None:
    if doc_type not in ROLE_DOC_TYPES.get(role, []):
        raise UploadRejected("Tu rol no puede subir ese tipo de documento.", "type_not_allowed")


# ------------------------------ Validar PDF ------------------------------
def validate_pdf(data: bytes, filename: str | None) -> None:
    """Revisa extensión, tamaño y 'firma' del archivo. No confía en el Content-Type del navegador."""
    if not filename or not filename.lower().endswith(".pdf"):
        raise UploadRejected("Solo se aceptan archivos PDF (.pdf).", "not_pdf")
    if not data:
        raise UploadRejected("El archivo está vacío.", "empty")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise UploadRejected(f"El archivo supera el máximo de {max_mb()} MB.", "too_large")
    if not data.startswith(PDF_MAGIC):
        raise UploadRejected("El archivo no es un PDF válido.", "not_pdf")
    if PDF_EOF not in data[-1024:]:
        raise UploadRejected("El PDF parece incompleto o dañado.", "pdf_truncated")


# ------------------------- Cifrar + guardar metadatos -------------------------
def _documents_dir() -> Path:
    return Path(os.environ.get("DOCUMENTS_DIR", "/srv/data/documents"))


def _remove_encrypted(storage_path: str) -> None:
    """Borra el .gpg si Mongo falló (evita archivos huérfanos sin metadato)."""
    if _STORAGE_RE.match(storage_path):
        (_documents_dir() / storage_path.split("/", 1)[1]).unlink(missing_ok=True)


def store_document(mongo_db: Database, data: bytes, *, uploader_id: int,
                   student_id: int, doc_type: str) -> str:
    """1) cifra con GPG -> <uuid>.gpg  2) inserta document_metadata. Devuelve storage_path.
    Es bloqueante (gpg + Mongo): la ruta la llama con run_in_threadpool."""
    storage_path = security.encrypt_document(data)
    metadata = {
        "type": doc_type,
        "upload_date": datetime.now(timezone.utc),
        "uploader_id": uploader_id,   # users.user_id
        "student_ref": student_id,    # students.student_id (solo el ID)
        "storage_path": storage_path,
    }
    try:
        mongo_db["document_metadata"].insert_one(metadata)
    except PyMongoError:
        _remove_encrypted(storage_path)
        raise
    return storage_path


# ---------------------------------- Lista ----------------------------------
def _names_by_id(db: Connection, sql: str, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    stmt = text(sql).bindparams(bindparam("ids", expanding=True))
    return {r["id"]: r["name"] for r in db.execute(stmt, {"ids": sorted(ids)}).mappings().all()}


def _local_time(ts) -> str:
    if not isinstance(ts, datetime):
        return "—"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)  # Mongo guarda en UTC
    return ts.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")


def list_documents(mongo_db: Database, db: Connection, user: SessionUser) -> list[dict]:
    """Admin ve todos; docente solo los que él subió. Los nombres salen de MySQL."""
    query = {} if user.role == "admin" else {"uploader_id": user.user_id}
    projection = {"type": 1, "upload_date": 1, "uploader_id": 1, "student_ref": 1, "storage_path": 1}
    docs = list(mongo_db["document_metadata"].find(query, projection)
                .sort("upload_date", -1).limit(LIST_LIMIT))

    students = _names_by_id(db, """
        SELECT student_id AS id, CONCAT(last_name, ' ', first_name) AS name
          FROM students WHERE student_id IN :ids""",
        {d["student_ref"] for d in docs if isinstance(d.get("student_ref"), int)})
    uploaders = _names_by_id(db, """
        SELECT user_id AS id, username AS name
          FROM users WHERE user_id IN :ids""",
        {d["uploader_id"] for d in docs if isinstance(d.get("uploader_id"), int)})

    return [{
        "uploaded_at": _local_time(d.get("upload_date")),
        "type_label": DOC_TYPES.get(d.get("type"), d.get("type")),
        "student_id": d.get("student_ref"),
        "student_name": students.get(d.get("student_ref"), f"ID {d.get('student_ref')}"),
        "uploader": uploaders.get(d.get("uploader_id"), f"ID {d.get('uploader_id')}"),
        "storage_path": d.get("storage_path"),
    } for d in docs]
