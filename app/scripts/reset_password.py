"""Restablece la contraseña de una cuenta (o de todas) y DEJA EVENTO en la auditoría.
Control del riesgo R25: un cambio hecho fuera de la app ya no queda sin rastro.

Uso (desde la raíz del repo, con los contenedores arriba):
  read -rs -p "Nueva contraseña: " NEW_PASSWORD; echo; export NEW_PASSWORD
  docker compose exec -e NEW_PASSWORD app python -m app.scripts.reset_password --user lgomez
  docker compose exec -e NEW_PASSWORD app python -m app.scripts.reset_password --all
  unset NEW_PASSWORD

- La contraseña llega por variable de entorno (no queda en el historial de bash).
- Cada cuenta recibe su propio hash Argon2 (sal distinta) y se desbloquea.
- El MFA NO cambia: el usuario sigue usando su app de códigos.
"""
import argparse
import os
import sys

from sqlalchemy import text

from app import security
from app.db import get_engine
from app.services.audit_service import AuditAction, record

MIN_LENGTH = 12  # misma regla que el formulario de usuarios (models/forms.py)


def reset(db, password: str, username: str | None) -> list[int]:
    """Actualiza los hashes. username=None => todas las cuentas. Devuelve los user_id cambiados."""
    if username is None:
        rows = db.execute(text("SELECT user_id FROM users ORDER BY user_id")).all()
    else:
        rows = db.execute(text("SELECT user_id FROM users WHERE username = :u"), {"u": username}).all()
    ids = [r[0] for r in rows]
    for uid in ids:
        db.execute(text("""
            UPDATE users SET password_hash = :h, failed_attempts = 0, locked_until = NULL
             WHERE user_id = :uid
        """), {"h": security.hash_password(password), "uid": uid})
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restablece contraseñas con registro en la auditoría.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--user", help="username de la cuenta")
    target.add_argument("--all", action="store_true", help="todas las cuentas")
    args = parser.parse_args(argv)

    password = os.environ.get("NEW_PASSWORD", "")
    if len(password) < MIN_LENGTH:
        print(f"Define NEW_PASSWORD con al menos {MIN_LENGTH} caracteres.", file=sys.stderr)
        return 2

    with get_engine().begin() as db:  # todo o nada
        ids = reset(db, password, None if args.all else args.user)
    if not ids:
        print("No existe esa cuenta. No se cambió nada.", file=sys.stderr)
        return 1

    # Auditoría: solo IDs y códigos. user_id=None porque no lo hace un usuario de la app.
    details = {"change": "password_reset_cli", "count": len(ids)}
    if not args.all:
        details["target_user_id"] = ids[0]
    record(AuditAction.USER_UPDATED, user_id=None, ip=None, details=details)
    print(f"Contraseña restablecida en {len(ids)} cuenta(s). Evento user_updated registrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
