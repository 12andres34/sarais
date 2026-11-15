"""Gestión de usuarios (solo admin). Todas las consultas son parametrizadas (:nombre)."""
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from app import security
from app.models.forms import UserCreateForm
from app.services.errors import ServiceError


def dashboard_counts(db: Connection) -> dict:
    return dict(db.execute(text("""
        SELECT (SELECT COUNT(*) FROM users WHERE is_active = 1)            AS active_users,
               (SELECT COUNT(*) FROM students WHERE status = 'active')     AS active_students,
               (SELECT COUNT(*) FROM teachers WHERE is_active = 1)         AS active_teachers,
               (SELECT COUNT(*) FROM enrollments WHERE status = 'active')  AS active_enrollments,
               (SELECT COUNT(*) FROM users
                 WHERE locked_until IS NOT NULL AND locked_until > NOW())  AS locked_users
    """)).mappings().one())


def list_users(db: Connection) -> list[dict]:
    rows = db.execute(text("""
        SELECT u.user_id, u.username, u.email, r.role_name, u.is_active, u.mfa_enabled,
               (u.locked_until IS NOT NULL AND u.locked_until > NOW()) AS is_locked,
               u.last_login_at,
               COALESCE(CONCAT(s.last_name, ' ', s.first_name),
                        CONCAT(t.last_name, ' ', t.first_name)) AS person_name
          FROM users u
          JOIN roles r         ON r.role_id = u.role_id
          LEFT JOIN students s ON s.user_id = u.user_id
          LEFT JOIN teachers t ON t.user_id = u.user_id
         ORDER BY r.role_name, u.username
    """)).mappings().all()
    return [dict(r) for r in rows]


def list_unlinked_students(db: Connection) -> list[dict]:
    rows = db.execute(text("""
        SELECT student_id, document_number, last_name, first_name
          FROM students
         WHERE user_id IS NULL AND status = 'active'
         ORDER BY last_name, first_name
    """)).mappings().all()
    return [dict(r) for r in rows]


def list_unlinked_teachers(db: Connection) -> list[dict]:
    rows = db.execute(text("""
        SELECT teacher_id, document_number, last_name, first_name
          FROM teachers
         WHERE user_id IS NULL AND is_active = 1
         ORDER BY last_name, first_name
    """)).mappings().all()
    return [dict(r) for r in rows]


def create_user(db: Connection, form: UserCreateForm) -> int:
    role_id = db.execute(text("SELECT role_id FROM roles WHERE role_name = :r"),
                         {"r": form.role}).scalar_one_or_none()
    if role_id is None:
        raise ServiceError("El rol no existe en la base de datos.")
    password_hash = security.hash_password(form.password)  # Argon2, lo hace el módulo de seguridad

    try:
        # SAVEPOINT: si algo falla, se deshace el INSERT y el vínculo juntos
        with db.begin_nested():
            result = db.execute(text("""
                INSERT INTO users (role_id, username, email, password_hash)
                VALUES (:role_id, :username, :email, :password_hash)
            """), {"role_id": role_id, "username": form.username,
                   "email": form.email.lower(), "password_hash": password_hash})
            new_id = result.lastrowid

            if form.student_id is not None:
                linked = db.execute(text("""
                    UPDATE students SET user_id = :uid
                     WHERE student_id = :sid AND user_id IS NULL
                """), {"uid": new_id, "sid": form.student_id})
                if linked.rowcount != 1:
                    raise ServiceError("El estudiante no existe o ya tiene una cuenta.")

            if form.teacher_id is not None:
                linked = db.execute(text("""
                    UPDATE teachers SET user_id = :uid
                     WHERE teacher_id = :tid AND user_id IS NULL
                """), {"uid": new_id, "tid": form.teacher_id})
                if linked.rowcount != 1:
                    raise ServiceError("El docente no existe o ya tiene una cuenta.")
    except IntegrityError:
        raise ServiceError("El nombre de usuario o el correo ya existen.")
    return new_id


def toggle_active(db: Connection, target_id: int, actor_id: int) -> bool:
    if target_id == actor_id:
        raise ServiceError("No puedes desactivar tu propia cuenta.")
    result = db.execute(text("UPDATE users SET is_active = 1 - is_active WHERE user_id = :uid"),
                        {"uid": target_id})
    if result.rowcount != 1:
        raise ServiceError("El usuario no existe.")
    return bool(db.execute(text("SELECT is_active FROM users WHERE user_id = :uid"),
                           {"uid": target_id}).scalar_one())


def unlock(db: Connection, target_id: int) -> None:
    result = db.execute(text("""
        UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE user_id = :uid
    """), {"uid": target_id})
    if result.rowcount == 0 and not _exists(db, target_id):
        raise ServiceError("El usuario no existe.")


def reset_mfa(db: Connection, target_id: int) -> None:
    """El usuario deberá registrar MFA de nuevo en su próximo inicio de sesión."""
    result = db.execute(text("""
        UPDATE users SET mfa_enabled = 0, mfa_secret_encrypted = NULL WHERE user_id = :uid
    """), {"uid": target_id})
    if result.rowcount == 0 and not _exists(db, target_id):
        raise ServiceError("El usuario no existe.")


def _exists(db: Connection, user_id: int) -> bool:
    return db.execute(text("SELECT 1 FROM users WHERE user_id = :uid"),
                      {"uid": user_id}).first() is not None
