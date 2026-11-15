"""Matrículas (solo admin)."""
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from app.models.forms import EnrollmentCreateForm
from app.services.errors import ServiceError


def list_class_groups(db: Connection) -> list[dict]:
    rows = db.execute(text("""
        SELECT class_group_id, academic_year, grade_level, section
          FROM class_groups
         ORDER BY academic_year DESC, grade_level, section
    """)).mappings().all()
    return [dict(r) for r in rows]


def list_active_students(db: Connection) -> list[dict]:
    rows = db.execute(text("""
        SELECT student_id, document_number, last_name, first_name
          FROM students WHERE status = 'active'
         ORDER BY last_name, first_name
    """)).mappings().all()
    return [dict(r) for r in rows]


def list_enrollments(db: Connection, class_group_id: int | None) -> list[dict]:
    # El filtro opcional se arma con un parámetro, nunca concatenando texto del usuario
    rows = db.execute(text("""
        SELECT e.enrollment_id, e.enrollment_date, e.status,
               s.document_number, CONCAT(s.last_name, ' ', s.first_name) AS student_name,
               cg.academic_year, cg.grade_level, cg.section
          FROM enrollments e
          JOIN students s      ON s.student_id = e.student_id
          JOIN class_groups cg ON cg.class_group_id = e.class_group_id
         WHERE (:cg IS NULL OR e.class_group_id = :cg)
         ORDER BY cg.academic_year DESC, cg.grade_level, cg.section, s.last_name, s.first_name
         LIMIT 300
    """), {"cg": class_group_id}).mappings().all()
    return [dict(r) for r in rows]


def create_enrollment(db: Connection, form: EnrollmentCreateForm) -> int:
    year = db.execute(text("SELECT academic_year FROM class_groups WHERE class_group_id = :cg"),
                      {"cg": form.class_group_id}).scalar_one_or_none()
    if year is None:
        raise ServiceError("El curso no existe.")

    status = db.execute(text("SELECT status FROM students WHERE student_id = :sid"),
                        {"sid": form.student_id}).scalar_one_or_none()
    if status != "active":
        raise ServiceError("El estudiante no existe o no está activo.")

    # Regla que el esquema no controla: una sola matrícula activa por estudiante y año
    already = db.execute(text("""
        SELECT COUNT(*) FROM enrollments e
          JOIN class_groups cg ON cg.class_group_id = e.class_group_id
         WHERE e.student_id = :sid AND cg.academic_year = :y AND e.status = 'active'
    """), {"sid": form.student_id, "y": year}).scalar_one()
    if already:
        raise ServiceError(f"El estudiante ya tiene una matrícula activa en {year}.")

    try:
        with db.begin_nested():
            result = db.execute(text("""
                INSERT INTO enrollments (student_id, class_group_id, enrollment_date)
                VALUES (:sid, :cg, :d)
            """), {"sid": form.student_id, "cg": form.class_group_id, "d": form.enrollment_date})
    except IntegrityError:
        raise ServiceError("El estudiante ya está matriculado en ese curso.")
    return result.lastrowid


def update_status(db: Connection, enrollment_id: int, status: str) -> None:
    exists = db.execute(text("SELECT 1 FROM enrollments WHERE enrollment_id = :eid"),
                        {"eid": enrollment_id}).first()
    if exists is None:
        raise ServiceError("La matrícula no existe.")
    db.execute(text("UPDATE enrollments SET status = :st WHERE enrollment_id = :eid"),
               {"st": status, "eid": enrollment_id})
