"""Estudiante: boletín y asistencia. Siempre con el student_id de la SESIÓN (no de la URL)."""
from collections import OrderedDict

from sqlalchemy import text
from sqlalchemy.engine import Connection


def report_card(db: Connection, student_id: int) -> list[dict]:
    """Agrupa la vista v_report_card por año y periodo."""
    rows = db.execute(text("""
        SELECT academic_year, period_number, class_group, subject_name, area,
               teacher_name, score, performance_level, absences, observation
          FROM v_report_card
         WHERE student_id = :sid
         ORDER BY academic_year DESC, period_number, area, subject_name
    """), {"sid": student_id}).mappings().all()

    groups: "OrderedDict[tuple, dict]" = OrderedDict()
    for r in rows:
        key = (r["academic_year"], r["period_number"])
        if key not in groups:
            groups[key] = {"academic_year": r["academic_year"], "period_number": r["period_number"],
                           "class_group": r["class_group"], "rows": []}
        groups[key]["rows"].append(dict(r))
    for g in groups.values():
        scores = [float(r["score"]) for r in g["rows"]]
        g["average"] = round(sum(scores) / len(scores), 2) if scores else None
    return list(groups.values())


def attendance_summary(db: Connection, student_id: int) -> dict:
    rows = db.execute(text("""
        SELECT a.status, COUNT(*) AS total
          FROM attendance a
          JOIN enrollments e ON e.enrollment_id = a.enrollment_id
         WHERE e.student_id = :sid
         GROUP BY a.status
    """), {"sid": student_id}).mappings().all()
    summary = {"present": 0, "absent": 0, "late": 0, "excused": 0}
    for r in rows:
        summary[r["status"]] = r["total"]
    return summary


def attendance_records(db: Connection, student_id: int, limit: int = 200) -> list[dict]:
    rows = db.execute(text("""
        SELECT a.class_date, sub.subject_name, a.status, a.notes
          FROM attendance a
          JOIN enrollments e           ON e.enrollment_id = a.enrollment_id
          JOIN teaching_assignments ta ON ta.assignment_id = a.assignment_id
          JOIN subjects sub            ON sub.subject_id = ta.subject_id
         WHERE e.student_id = :sid
         ORDER BY a.class_date DESC, sub.subject_name
         LIMIT :lim
    """), {"sid": student_id, "lim": limit}).mappings().all()
    return [dict(r) for r in rows]
