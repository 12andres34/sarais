"""Pantallas del administrador: usuarios, matrículas y auditoría."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pymongo.errors import PyMongoError
from sqlalchemy.engine import Connection

from app.db import get_db, get_mongo_db
from app.deps import ADMIN
from app.models.forms import AuditFilter, EnrollmentCreateForm, EnrollmentStatusForm, UserCreateForm
from app.services import audit_service, enrollment_service, user_service
from app.services.audit_service import AuditAction, record
from app.services.auth_service import SessionUser
from app.services.errors import ServiceError
from app.config import today_local
from app.web import client_ip, flash, parse_optional_int, read_form, render, validate

router = APIRouter(prefix="/admin")


@router.get("")
def dashboard(request: Request, user: SessionUser = Depends(ADMIN), db: Connection = Depends(get_db)):
    return render(request, "admin/dashboard.html", {"counts": user_service.dashboard_counts(db)})


# ------------------------------ Usuarios ------------------------------
@router.get("/users")
def users_page(request: Request, user: SessionUser = Depends(ADMIN), db: Connection = Depends(get_db)):
    return render(request, "admin/users.html", {
        "users": user_service.list_users(db),
        "free_students": user_service.list_unlinked_students(db),
        "free_teachers": user_service.list_unlinked_teachers(db),
    })


@router.post("/users")
async def create_user(request: Request, user: SessionUser = Depends(ADMIN), db: Connection = Depends(get_db)):
    data = await read_form(request)
    form, error = validate(UserCreateForm, data)
    if error:
        flash(request, f"Datos inválidos: {error}", "error")
        return RedirectResponse("/admin/users", status_code=303)
    try:
        new_id = user_service.create_user(db, form)
    except ServiceError as exc:
        flash(request, str(exc), "error")
        return RedirectResponse("/admin/users", status_code=303)
    record(AuditAction.USER_CREATED, user_id=user.user_id, ip=client_ip(request),
           details={"target_user_id": new_id, "role": form.role})
    flash(request, f"Usuario '{form.username}' creado. Registrará MFA en su primer ingreso.", "success")
    return RedirectResponse("/admin/users", status_code=303)


async def _user_action(request: Request, user: SessionUser, db: Connection, target_id: int, action: str):
    await read_form(request)
    try:
        if action == "toggle":
            active = user_service.toggle_active(db, target_id, user.user_id)
            change, msg = "is_active", ("Usuario activado." if active else "Usuario desactivado.")
            audit_action = AuditAction.USER_UPDATED
        elif action == "unlock":
            user_service.unlock(db, target_id)
            change, msg, audit_action = "unlock", "Usuario desbloqueado.", AuditAction.USER_UPDATED
        else:
            user_service.reset_mfa(db, target_id)
            change, msg, audit_action = "mfa_reset", "MFA reiniciado.", AuditAction.MFA_RESET
    except ServiceError as exc:
        flash(request, str(exc), "error")
        return RedirectResponse("/admin/users", status_code=303)
    record(audit_action, user_id=user.user_id, ip=client_ip(request),
           details={"target_user_id": target_id, "change": change})
    flash(request, msg, "success")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{target_id}/toggle-active")
async def toggle_active(request: Request, target_id: int, user: SessionUser = Depends(ADMIN),
                        db: Connection = Depends(get_db)):
    return await _user_action(request, user, db, target_id, "toggle")


@router.post("/users/{target_id}/unlock")
async def unlock(request: Request, target_id: int, user: SessionUser = Depends(ADMIN),
                 db: Connection = Depends(get_db)):
    return await _user_action(request, user, db, target_id, "unlock")


@router.post("/users/{target_id}/reset-mfa")
async def reset_mfa(request: Request, target_id: int, user: SessionUser = Depends(ADMIN),
                    db: Connection = Depends(get_db)):
    return await _user_action(request, user, db, target_id, "reset_mfa")


# ----------------------------- Matrículas -----------------------------
@router.get("/enrollments")
def enrollments_page(request: Request, class_group_id: str | None = None,
                     user: SessionUser = Depends(ADMIN), db: Connection = Depends(get_db)):
    selected = parse_optional_int(class_group_id)
    return render(request, "admin/enrollments.html", {
        "groups": enrollment_service.list_class_groups(db),
        "students": enrollment_service.list_active_students(db),
        "enrollments": enrollment_service.list_enrollments(db, selected),
        "selected_group": selected,
        "today": today_local().isoformat(),
    })


@router.post("/enrollments")
async def create_enrollment(request: Request, user: SessionUser = Depends(ADMIN),
                            db: Connection = Depends(get_db)):
    data = await read_form(request)
    form, error = validate(EnrollmentCreateForm, data)
    back = "/admin/enrollments"
    if error:
        flash(request, f"Datos inválidos: {error}", "error")
        return RedirectResponse(back, status_code=303)
    try:
        new_id = enrollment_service.create_enrollment(db, form)
    except ServiceError as exc:
        flash(request, str(exc), "error")
        return RedirectResponse(back, status_code=303)
    record(AuditAction.ENROLLMENT_CREATED, user_id=user.user_id, ip=client_ip(request),
           details={"enrollment_id": new_id, "student_id": form.student_id,
                    "class_group_id": form.class_group_id})
    flash(request, "Matrícula creada.", "success")
    return RedirectResponse(f"{back}?class_group_id={form.class_group_id}", status_code=303)


@router.post("/enrollments/{enrollment_id}/status")
async def change_enrollment_status(request: Request, enrollment_id: int, user: SessionUser = Depends(ADMIN),
                                   db: Connection = Depends(get_db)):
    data = await read_form(request)
    form, error = validate(EnrollmentStatusForm, data)
    if error:
        flash(request, "Estado inválido.", "error")
    else:
        try:
            enrollment_service.update_status(db, enrollment_id, form.status)
            record(AuditAction.ENROLLMENT_UPDATED, user_id=user.user_id, ip=client_ip(request),
                   details={"enrollment_id": enrollment_id, "status": form.status})
            flash(request, "Estado de la matrícula actualizado.", "success")
        except ServiceError as exc:
            flash(request, str(exc), "error")
    # Volver al mismo filtro de curso (dato validado como entero)
    group = parse_optional_int(data.get("return_group"))
    url = f"/admin/enrollments?class_group_id={group}" if group else "/admin/enrollments"
    return RedirectResponse(url, status_code=303)


# ------------------------------ Auditoría ------------------------------
@router.get("/audit")
def audit_page(request: Request, action: str | None = None, user_id: str | None = None, page: str | None = None,
               user: SessionUser = Depends(ADMIN)):
    filters, error = validate(AuditFilter, {"action": action, "user_id": user_id, "page": page})
    if error or (filters.action and filters.action not in AuditAction.ALL):
        flash(request, "Filtro inválido.", "error")
        filters = AuditFilter()
    rows, has_more, mongo_error = [], False, None
    try:
        rows, has_more = audit_service.list_logs(get_mongo_db(), filters.action, filters.user_id, filters.page)
    except PyMongoError:
        mongo_error = "No se pudo consultar MongoDB. Revisa que el servicio esté activo."
    return render(request, "admin/audit.html", {
        "rows": rows, "has_more": has_more, "filters": filters,
        "actions": AuditAction.ALL, "mongo_error": mongo_error,
    })
