"""Subida y lista de documentos (PDF cifrados con GPG). Solo admin y docente."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pymongo.errors import PyMongoError
from sqlalchemy.engine import Connection
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.db import get_db, get_mongo_db
from app.deps import require_role
from app.models.forms import DocumentUploadForm
from app.security.crypto import MAX_DOCUMENT_BYTES
from app.services import document_service
from app.services.audit_service import AuditAction, record
from app.services.auth_service import SessionUser
from app.services.document_service import UploadRejected
from app.web import client_ip, flash, read_upload_form, render, validate

logger = logging.getLogger("sarais.documents")
router = APIRouter(prefix="/documents")

UPLOADERS = require_role("admin", "teacher")
FORM_OVERHEAD = 64 * 1024  # bytes extra del formulario (campos, separadores multipart)
BACK = "/documents"


def _uploader(user: SessionUser = Depends(UPLOADERS)) -> SessionUser:
    """Rol admin/teacher y, si es docente, cuenta vinculada a un docente."""
    if user.role == "teacher" and user.teacher_id is None:
        raise HTTPException(status_code=403, detail="Tu cuenta no está vinculada a un docente.")
    return user


def _audit_failure(user: SessionUser, ip: str | None, reason: str, student_id: int | None = None) -> None:
    details = {"reason": reason}
    if student_id is not None:
        details["student_id"] = student_id
    record(AuditAction.DOCUMENT_UPLOADED, user_id=user.user_id, ip=ip, success=False, details=details)


@router.get("")
def documents_page(request: Request, user: SessionUser = Depends(_uploader),
                   db: Connection = Depends(get_db)):
    documents, mongo_error = [], None
    try:
        documents = document_service.list_documents(get_mongo_db(), db, user)
    except PyMongoError:
        mongo_error = "No se pudo consultar MongoDB. Revisa que el servicio esté activo."
    return render(request, "documents/index.html", {
        "students": document_service.list_uploadable_students(db, user),
        "doc_types": document_service.allowed_types(user.role),
        "documents": documents,
        "mongo_error": mongo_error,
        "max_mb": document_service.max_mb(),
        "is_admin": user.role == "admin",
    })


@router.post("")
async def upload_document(request: Request, user: SessionUser = Depends(_uploader),
                          db: Connection = Depends(get_db)):
    ip = client_ip(request)

    # 1) Antes de leer el cuerpo: tipo de formulario y tamaño declarado
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise HTTPException(status_code=400, detail="El formulario debe enviarse como multipart/form-data.")
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_DOCUMENT_BYTES + FORM_OVERHEAD:
        _audit_failure(user, ip, "too_large")
        raise HTTPException(status_code=413)

    # 2) Leer el formulario y verificar CSRF (máximo 1 archivo)
    data, form = await read_upload_form(request)
    student_id = None
    try:
        fields, error = validate(DocumentUploadForm, data)
        if error:
            raise UploadRejected("Datos inválidos: elige estudiante y tipo de documento.", "invalid_form")
        student_id = fields.student_id
        document_service.ensure_type_allowed(user.role, fields.doc_type)
        document_service.ensure_student_allowed(db, user, student_id)

        upload = form.get("document")
        if not isinstance(upload, UploadFile):
            raise UploadRejected("Selecciona un archivo PDF.", "no_file")
        content = await upload.read(MAX_DOCUMENT_BYTES + 1)  # +1 para detectar si se pasa
        document_service.validate_pdf(content, upload.filename)

        # 3) Cifrar con GPG + guardar metadatos (bloqueante: fuera del event loop)
        storage_path = await run_in_threadpool(
            document_service.store_document, get_mongo_db(), content,
            uploader_id=user.user_id, student_id=student_id, doc_type=fields.doc_type)
    except UploadRejected as exc:
        _audit_failure(user, ip, exc.reason, student_id)
        flash(request, str(exc), "error")
        return RedirectResponse(BACK, status_code=303)
    except (RuntimeError, ValueError, PyMongoError):
        # gpg sin llave, carpeta inexistente, Mongo caído... El detalle va al log, no al navegador
        logger.exception("Fallo al guardar documento")
        _audit_failure(user, ip, "storage_error", student_id)
        flash(request, "No se pudo guardar el documento. Avisa al administrador.", "error")
        return RedirectResponse(BACK, status_code=303)
    finally:
        await form.close()  # borra el archivo temporal de Starlette

    # 4) Auditoría: solo IDs y códigos
    record(AuditAction.DOCUMENT_UPLOADED, user_id=user.user_id, ip=ip, details={
        "student_id": student_id, "doc_type": fields.doc_type,
        "storage_path": storage_path, "size_bytes": len(content),
    })
    flash(request, "Documento cifrado y guardado.", "success")
    return RedirectResponse(BACK, status_code=303)
