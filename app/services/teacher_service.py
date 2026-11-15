"""Docente: sus grupos, notas y asistencia.
Regla clave: toda consulta filtra por el teacher_id de la SESIÓN, nunca por uno del formulario."""
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.models.forms import AttendanceEntry, GradeEntry
from app.services.audit_service import AuditAction, record
from app.services.errors import ServiceError
from app.web import format_errors
from pydantic import ValidationError

ATTENDANCE_STATUSES = [("present", "Presente"), ("absent", "Ausente"),
                       ("late", "Tarde"), ("excused", "Excusa")]


def list_assignments(db: Connection, teacher_id: int) -> list[dict]:
    rows = db.execute(text("""
        SELECT ta.assignment_id, sub.subject_name,
               cg.class_group_id, cg.academic_year, cg.grade_level, cg.section,
               (SELECT COUNT(*) FROM enrollments e
                 WHERE e.class_group_id = cg.class_group_id AND e.status = 'active') AS students
          FROM teaching_assignments ta
          JOIN subjects sub    ON sub.subject_id = ta.subject_id
          JOIN class_groups cg ON cg.class_group_id = ta.class_group_id
         WHERE ta.teacher_id = :tid
         ORDER BY cg.academic_year DESC, cg.grade_level, cg.section, sub.subject_name
    """), {"tid": teacher_id}).mappings().all()
    return [dict(r) for r in rows]


def get_owned_assignment(db: Connection, teacher_id: int, assignment_id: int) -> dict:
    """Devuelve la asignación SOLO si es del docente. Si no, 403 (evita ver grupos ajenos)."""
    row = db.execute(text("""
        SELECT ta.assignment_id, ta.class_group_id, sub.subject_name,
               cg.academic_year, cg.grade_level, cg.section
          FROM teaching_assignments ta
          JOIN subjects sub    ON sub.subject_id = ta.subject_id
          JOIN class_groups cg ON cg.class_group_id = ta.class_group_id
         WHERE ta.assignment_id = :aid AND ta.teacher_id = :tid
    """), {"aid": assignment_id, "tid": teacher_id}).mappings().first()
    if row is None:
        raise HTTPException(status_code=403, detail="No tienes acceso a este grupo.")
    return dict(row)


def list_periods(db: Connection, academic_year: int) -> list[dict]:
    rows = db.execute(text("""
        SELECT period_id, period_number, start_date, end_date, is_closed
          FROM periods WHERE academic_year = :y ORDER BY period_number
    """), {"y": academic_year}).mappings().all()
    return [dict(r) for r in rows]


def default_period_id(periods: list[dict]) -> int | None:
    open_periods = [p for p in periods if not p["is_closed"]]
    chosen = open_periods[0] if open_periods else (periods[-1] if periods else None)
    return chosen["period_id"] if chosen else None


def get_period(db: Connection, assignment: dict, period_id: int | None) -> dict:
    row = db.execute(text("""
        SELECT period_id, period_number, is_closed FROM periods
         WHERE period_id = :pid AND academic_year = :y
    """), {"pid": period_id, "y": assignment["academic_year"]}).mappings().first()
    if row is None:
        raise ServiceError("El periodo no corresponde al año del curso.")
    return dict(row)


# ------------------------------- Notas -------------------------------
def roster_with_grades(db: Connection, assignment: dict, period_id: int) -> list[dict]:
    rows = db.execute(text("""
        SELECT e.enrollment_id, s.document_number,
               CONCAT(s.last_name, ' ', s.first_name) AS student_name,
               g.score, g.observation
          FROM enrollments e
          JOIN students s     ON s.student_id = e.student_id
          LEFT JOIN grades g  ON g.enrollment_id = e.enrollment_id
                             AND g.assignment_id = :aid AND g.period_id = :pid
         WHERE e.class_group_id = :cg AND e.status = 'active'
         ORDER BY s.last_name, s.first_name
    """), {"aid": assignment["assignment_id"], "pid": period_id,
           "cg": assignment["class_group_id"]}).mappings().all()
    return [dict(r) for r in rows]


def parse_grade_form(roster: list[dict], data: dict[str, str]) -> tuple[dict[int, GradeEntry], list[str]]:
    """Lee score_<id>/obs_<id> SOLO para los estudiantes del curso (ignora IDs inventados).
    Nota vacía = no se modifica."""
    entries, errors = {}, []
    for student in roster:
        eid = student["enrollment_id"]
        raw_score = (data.get(f"score_{eid}") or "").strip()
        if raw_score == "":
            continue
        try:
            entries[eid] = GradeEntry(score=raw_score, observation=data.get(f"obs_{eid}"))
        except ValidationError as exc:
            errors.append(f"{student['student_name']}: {format_errors(exc)}")
    return entries, errors


def save_grades(db: Connection, assignment: dict, period: dict, entries: dict[int, GradeEntry],
                actor_id: int, ip: str | None) -> int:
    if period["is_closed"]:
        raise ServiceError("El periodo está cerrado: no se pueden modificar notas.")
    existing = {
        r["enrollment_id"]: r for r in db.execute(text("""
            SELECT grade_id, enrollment_id, score, observation FROM grades
             WHERE assignment_id = :aid AND period_id = :pid
        """), {"aid": assignment["assignment_id"], "pid": period["period_id"]}).mappings()
    }
    changed = 0
    for eid, entry in entries.items():
        old = existing.get(eid)
        if old is None:
            db.execute(text("""
                INSERT INTO grades (enrollment_id, assignment_id, period_id, score, observation)
                VALUES (:eid, :aid, :pid, :score, :obs)
            """), {"eid": eid, "aid": assignment["assignment_id"], "pid": period["period_id"],
                   "score": entry.score, "obs": entry.observation})
        elif Decimal(old["score"]) != entry.score or (old["observation"] or None) != entry.observation:
            db.execute(text("""
                UPDATE grades SET score = :score, observation = :obs WHERE grade_id = :gid
            """), {"score": entry.score, "obs": entry.observation, "gid": old["grade_id"]})
        else:
            continue  # sin cambios: no se audita
        changed += 1
        record(AuditAction.GRADE_CHANGE, user_id=actor_id, ip=ip, details={
            "enrollment_id": eid,
            "assignment_id": assignment["assignment_id"],
            "period_id": period["period_id"],
            "old_score": float(old["score"]) if old else None,
            "new_score": float(entry.score),
        })
    return changed


# ----------------------------- Asistencia -----------------------------
def check_class_date(db: Connection, assignment: dict, class_date: date) -> None:
    """La fecha debe caer dentro de un periodo abierto del año del curso."""
    period = db.execute(text("""
        SELECT period_id, is_closed FROM periods
         WHERE academic_year = :y AND :d BETWEEN start_date AND end_date
    """), {"y": assignment["academic_year"], "d": class_date}).mappings().first()
    if period is None:
        raise ServiceError("La fecha no está dentro de ningún periodo del año del curso.")
    if period["is_closed"]:
        raise ServiceError("El periodo de esa fecha está cerrado.")


def roster_with_attendance(db: Connection, assignment: dict, class_date: date) -> list[dict]:
    rows = db.execute(text("""
        SELECT e.enrollment_id, s.document_number,
               CONCAT(s.last_name, ' ', s.first_name) AS student_name,
               a.status
          FROM enrollments e
          JOIN students s       ON s.student_id = e.student_id
          LEFT JOIN attendance a ON a.enrollment_id = e.enrollment_id
                                AND a.assignment_id = :aid AND a.class_date = :d
         WHERE e.class_group_id = :cg AND e.status = 'active'
         ORDER BY s.last_name, s.first_name
    """), {"aid": assignment["assignment_id"], "d": class_date,
           "cg": assignment["class_group_id"]}).mappings().all()
    return [dict(r) for r in rows]


def save_attendance(db: Connection, assignment: dict, class_date: date, roster: list[dict],
                    data: dict[str, str], actor_id: int, ip: str | None) -> int:
    check_class_date(db, assignment, class_date)
    saved = 0
    for student in roster:
        eid = student["enrollment_id"]
        raw = data.get(f"status_{eid}")
        if not raw:
            continue
        try:
            entry = AttendanceEntry(status=raw)
        except ValidationError:
            raise ServiceError(f"Estado de asistencia inválido para {student['student_name']}.")
        # UPSERT: si ya existe el registro de ese día, se actualiza
        db.execute(text("""
            INSERT INTO attendance (enrollment_id, assignment_id, class_date, status)
            VALUES (:eid, :aid, :d, :st) AS new
            ON DUPLICATE KEY UPDATE status = new.status
        """), {"eid": eid, "aid": assignment["assignment_id"], "d": class_date, "st": entry.status})
        saved += 1
    if saved:
        record(AuditAction.ATTENDANCE_RECORDED, user_id=actor_id, ip=ip, details={
            "assignment_id": assignment["assignment_id"],
            "class_date": class_date.isoformat(),
            "records": saved,
        })
    return saved
