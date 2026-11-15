"""Pantallas del docente. Solo ve y modifica los grupos que tiene asignados."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.engine import Connection

from app.config import today_local
from app.db import get_db
from app.deps import TEACHER
from app.models.forms import ClassDateForm
from app.services import teacher_service
from app.services.auth_service import SessionUser
from app.services.errors import ServiceError
from app.web import client_ip, flash, parse_optional_int, read_form, render, validate

router = APIRouter(prefix="/teacher")


def _teacher_id(user: SessionUser) -> int:
    if user.teacher_id is None:
        raise HTTPException(status_code=403, detail="Tu cuenta no está vinculada a un docente.")
    return user.teacher_id


@router.get("")
def dashboard(request: Request, user: SessionUser = Depends(TEACHER), db: Connection = Depends(get_db)):
    return render(request, "teacher/dashboard.html",
                  {"assignments": teacher_service.list_assignments(db, _teacher_id(user))})


# -------------------------------- Notas --------------------------------
@router.get("/assignments/{assignment_id}/grades")
def grades_page(request: Request, assignment_id: int, period_id: str | None = None,
                user: SessionUser = Depends(TEACHER), db: Connection = Depends(get_db)):
    assignment = teacher_service.get_owned_assignment(db, _teacher_id(user), assignment_id)
    periods = teacher_service.list_periods(db, assignment["academic_year"])
    selected = parse_optional_int(period_id) or teacher_service.default_period_id(periods)
    period = next((p for p in periods if p["period_id"] == selected), None)
    roster = teacher_service.roster_with_grades(db, assignment, period["period_id"]) if period else []
    return render(request, "teacher/grades.html", {
        "assignment": assignment, "periods": periods, "period": period, "roster": roster,
    })


@router.post("/assignments/{assignment_id}/grades")
async def save_grades(request: Request, assignment_id: int,
                      user: SessionUser = Depends(TEACHER), db: Connection = Depends(get_db)):
    data = await read_form(request)
    assignment = teacher_service.get_owned_assignment(db, _teacher_id(user), assignment_id)
    period_id = parse_optional_int(data.get("period_id"))
    back = f"/teacher/assignments/{assignment_id}/grades?period_id={period_id or ''}"
    try:
        period = teacher_service.get_period(db, assignment, period_id)
        roster = teacher_service.roster_with_grades(db, assignment, period["period_id"])
        entries, errors = teacher_service.parse_grade_form(roster, data)
        if errors:
            # Todo o nada: si una nota es inválida no se guarda ninguna
            flash(request, "No se guardó nada. " + " | ".join(errors), "error")
            return RedirectResponse(back, status_code=303)
        changed = teacher_service.save_grades(db, assignment, period, entries, user.user_id, client_ip(request))
        flash(request, f"Notas guardadas: {changed} cambio(s).", "success")
    except ServiceError as exc:
        flash(request, str(exc), "error")
    return RedirectResponse(back, status_code=303)


# ------------------------------ Asistencia ------------------------------
@router.get("/assignments/{assignment_id}/attendance")
def attendance_page(request: Request, assignment_id: int, class_date: str | None = None,
                    user: SessionUser = Depends(TEACHER), db: Connection = Depends(get_db)):
    assignment = teacher_service.get_owned_assignment(db, _teacher_id(user), assignment_id)
    form, error = validate(ClassDateForm, {"class_date": class_date or today_local()})
    if error:
        flash(request, "Fecha inválida: se muestra la de hoy.", "error")
        form = ClassDateForm(class_date=today_local())
    roster = teacher_service.roster_with_attendance(db, assignment, form.class_date)
    return render(request, "teacher/attendance.html", {
        "assignment": assignment, "class_date": form.class_date, "roster": roster,
        "statuses": teacher_service.ATTENDANCE_STATUSES, "today": today_local().isoformat(),
    })


@router.post("/assignments/{assignment_id}/attendance")
async def save_attendance(request: Request, assignment_id: int,
                          user: SessionUser = Depends(TEACHER), db: Connection = Depends(get_db)):
    data = await read_form(request)
    assignment = teacher_service.get_owned_assignment(db, _teacher_id(user), assignment_id)
    form, error = validate(ClassDateForm, {"class_date": data.get("class_date")})
    if error:
        flash(request, f"Fecha inválida: {error}", "error")
        return RedirectResponse(f"/teacher/assignments/{assignment_id}/attendance", status_code=303)
    back = f"/teacher/assignments/{assignment_id}/attendance?class_date={form.class_date.isoformat()}"
    try:
        roster = teacher_service.roster_with_attendance(db, assignment, form.class_date)
        saved = teacher_service.save_attendance(db, assignment, form.class_date, roster, data,
                                                user.user_id, client_ip(request))
        flash(request, f"Asistencia guardada: {saved} estudiante(s).", "success")
    except ServiceError as exc:
        flash(request, str(exc), "error")
    return RedirectResponse(back, status_code=303)
