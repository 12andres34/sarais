"""Carga de datos sintéticos de acceso.
1) Reemplaza ARGON2_HASH_PLACEHOLDER (de db/dml.sql) por hashes Argon2 reales.
2) Crea cuentas demo (admin.demo, docente.demo, estudiante.demo) si falta algún rol.

Uso (desde la raíz del repo, con los contenedores arriba):
  docker compose exec -e SEED_PASSWORD='UnaClaveDemoLarga2026' app python -m app.scripts.seed_data
La contraseña NUNCA va en el código: llega por variable de entorno.
"""
import argparse
import os
import sys

from sqlalchemy import text

from app import security
from app.config import get_settings
from app.db import get_engine

PLACEHOLDER = "ARGON2_HASH_PLACEHOLDER"

# Consultas fijas (sin armar SQL con texto variable)
FREE_PERSON_SQL = {
    "teacher": "SELECT teacher_id FROM teachers WHERE user_id IS NULL AND is_active = 1 ORDER BY teacher_id LIMIT 1",
    "student": "SELECT student_id FROM students WHERE user_id IS NULL AND status = 'active' ORDER BY student_id LIMIT 1",
}
LINK_SQL = {
    "teacher": "UPDATE teachers SET user_id = :uid WHERE teacher_id = :pid AND user_id IS NULL",
    "student": "UPDATE students SET user_id = :uid WHERE student_id = :pid AND user_id IS NULL",
}
DEMO_USERS = [("admin", "admin.demo"), ("teacher", "docente.demo"), ("student", "estudiante.demo")]


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga hashes reales y cuentas demo (datos sintéticos).")
    parser.add_argument("--allow-production", action="store_true", help="Permite ejecutar con APP_ENV=production")
    args = parser.parse_args()

    if get_settings().is_production and not args.allow_production:
        sys.exit("APP_ENV=production: no se cargan datos demo (usa --allow-production si es intencional).")

    password = os.environ.get("SEED_PASSWORD", "")
    if len(password) < 12:
        sys.exit("Define SEED_PASSWORD con al menos 12 caracteres.")

    with get_engine().begin() as db:  # todo en una transacción
        # 1) Hashes reales (cada uno con su propia sal aleatoria)
        pending = db.execute(text("SELECT user_id, username FROM users WHERE password_hash = :p"),
                             {"p": PLACEHOLDER}).mappings().all()
        for row in pending:
            db.execute(text("""
                UPDATE users SET password_hash = :h, failed_attempts = 0, locked_until = NULL
                 WHERE user_id = :uid
            """), {"h": security.hash_password(password), "uid": row["user_id"]})
        print(f"[seed] Hashes reemplazados: {len(pending)}")

        # 2) Cuentas demo solo si no existe ningún usuario con ese rol
        for role, username in DEMO_USERS:
            has_role = db.execute(text("""
                SELECT 1 FROM users u JOIN roles r ON r.role_id = u.role_id
                 WHERE r.role_name = :role LIMIT 1
            """), {"role": role}).first()
            if has_role:
                continue
            role_id = db.execute(text("SELECT role_id FROM roles WHERE role_name = :role"),
                                 {"role": role}).scalar_one_or_none()
            if role_id is None:
                print(f"[seed] Falta el rol '{role}' en la tabla roles: se omite.")
                continue
            person_id = None
            if role in FREE_PERSON_SQL:
                person_id = db.execute(text(FREE_PERSON_SQL[role])).scalar_one_or_none()
                if person_id is None:
                    print(f"[seed] No hay {role} sin cuenta para vincular: se omite {username}.")
                    continue
            result = db.execute(text("""
                INSERT INTO users (role_id, username, email, password_hash)
                VALUES (:rid, :u, :e, :h)
            """), {"rid": role_id, "u": username, "e": f"{username}@sarais.test",
                   "h": security.hash_password(password)})
            if person_id is not None:
                db.execute(text(LINK_SQL[role]), {"uid": result.lastrowid, "pid": person_id})
            print(f"[seed] Creado {username} ({role})")

        # 3) Resumen (sin contraseñas)
        rows = db.execute(text("""
            SELECT u.username, r.role_name,
                   COALESCE(t.teacher_id, s.student_id) AS person_id, u.mfa_enabled
              FROM users u
              JOIN roles r ON r.role_id = u.role_id
              LEFT JOIN teachers t ON t.user_id = u.user_id
              LEFT JOIN students s ON s.user_id = u.user_id
             ORDER BY r.role_name, u.username
        """)).mappings().all()
        print(f"\n{'usuario':<25}{'rol':<10}{'persona':<10}mfa")
        for r in rows:
            print(f"{r['username']:<25}{r['role_name']:<10}{str(r['person_id'] or '-'):<10}{'si' if r['mfa_enabled'] else 'pendiente'}")
    print("\n[seed] Listo. Todas las cuentas usan SEED_PASSWORD y registran MFA al entrar.")


if __name__ == "__main__":
    main()
