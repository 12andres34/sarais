"""Pantallas del estudiante. No reciben IDs por URL: solo se usa el de la sesión."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.engine import Connection

from app.db import get_db
from app.deps import STUDENT
from app.services import student_service
from app.services.auth_service import SessionUser
from app.web import render

router = APIRouter(prefix="/student")

STATUS_LABELS = {"present": "Presente", "absent": "Ausente", "late": "Tarde", "excused": "Excusa"}


def _student_id(user: SessionUser) -> int:
    if user.student_id is None:
        raise HTTPException(status_code=403, detail="Tu cuenta no está vinculada a un estudiante.")
    return user.student_id


@router.get("")
def report_card(request: Request, user: SessionUser = Depends(STUDENT), db: Connection = Depends(get_db)):
    return render(request, "student/report_card.html",
                  {"periods": student_service.report_card(db, _student_id(user))})


@router.get("/attendance")
def attendance(request: Request, user: SessionUser = Depends(STUDENT), db: Connection = Depends(get_db)):
    sid = _student_id(user)
    return render(request, "student/attendance.html", {
        "summary": student_service.attendance_summary(db, sid),
        "records": student_service.attendance_records(db, sid),
        "labels": STATUS_LABELS,
    })
