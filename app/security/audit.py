"""Auditoría solo-agregar en MongoDB (colección audit_logs)."""
from __future__ import annotations

import ipaddress
import json
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("sarais.audit")

# Debe coincidir con el enum del validador (db/mongo/init/01_init_mongo.js)
# y con AuditAction (app/services/audit_service.py)
AUDIT_ACTIONS = frozenset({
    "login_success", "login_failed", "mfa_failed", "mfa_enabled", "mfa_reset",
    "account_locked", "logout", "user_created", "user_updated",
    "enrollment_created", "enrollment_updated", "grade_change",
    "attendance_recorded", "document_uploaded",
})

# details: IDs y números. Texto solo en claves de "código" y sin espacios
# (nunca nombres, correos ni observaciones).
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_CODE_RE = re.compile(r"^[A-Za-z0-9_./-]{1,64}$")
_TEXT_KEYS = frozenset({"reason", "role", "change", "status", "class_date", "storage_path", "doc_type"})
_MAX_DETAILS = 10


def _get_collection():
    """Reutiliza el cliente de la app (app/db.py). Import tardío: evita ciclos."""
    from app.db import get_mongo_db
    return get_mongo_db()["audit_logs"]


def _clean_value(key: str, value: Any) -> tuple[bool, Any]:
    if value is None or isinstance(value, (bool, int)):
        return True, value
    if isinstance(value, float) and math.isfinite(value):
        return True, value          # p. ej. old_score / new_score
    if isinstance(value, str) and key in _TEXT_KEYS and _CODE_RE.match(value):
        return True, value
    return False, None              # texto libre, listas, dicts, etc.


def _clean_details(details: dict | None) -> dict[str, Any]:
    if not isinstance(details, dict):
        return {}
    clean: dict[str, Any] = {}
    dropped = 0
    for key, value in details.items():
        if len(clean) >= _MAX_DETAILS - 1 or not isinstance(key, str) or not _KEY_RE.match(key):
            dropped += 1
            continue
        ok, val = _clean_value(key, value)
        if ok:
            clean[key] = val
        else:
            dropped += 1
    if dropped:
        clean["dropped_keys"] = dropped
    return clean


def _clean_ip(ip: str | None) -> str | None:
    if not isinstance(ip, str):
        return None
    try:
        return str(ipaddress.ip_address(ip.strip()))
    except ValueError:
        return None


def audit_log(action: str, *, user_id: int | None, ip: str | None,
              success: bool, details: dict | None = None) -> None:
    """Inserta un evento en audit_logs. Nunca rompe la petición del usuario:
    si Mongo falla, el evento queda en el log del contenedor (AUDIT_FALLBACK)."""
    doc = {
        "timestamp": datetime.now(timezone.utc),
        "user_id": user_id if isinstance(user_id, int) and not isinstance(user_id, bool) else None,
        "action": action,
        "ip": _clean_ip(ip),
        "result": "success" if success else "failure",
        "details": _clean_details(details),
    }
    if action not in AUDIT_ACTIONS:
        logger.error("AUDIT_INVALID_ACTION %s", _as_json(doc))
        return
    try:
        _get_collection().insert_one(doc)
    except Exception as exc:  # Mongo caído, validador rechazó (121), etc.
        logger.error("AUDIT_FALLBACK %s error=%s", _as_json(doc), type(exc).__name__)


def _as_json(doc: dict) -> str:
    out = {k: v for k, v in doc.items() if k != "_id"}
    out["timestamp"] = doc["timestamp"].isoformat()
    return json.dumps(out, ensure_ascii=False)
