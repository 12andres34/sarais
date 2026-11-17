"""Auditoría: escribe con security.audit_log y lee audit_logs de MongoDB (solo lectura)."""
from pymongo.database import Database

from app import security


class AuditAction:
    """Acciones que usa la app. Deben coincidir con el enum del validador de Mongo."""
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    MFA_FAILED = "mfa_failed"
    MFA_ENABLED = "mfa_enabled"
    MFA_RESET = "mfa_reset"
    ACCOUNT_LOCKED = "account_locked"
    LOGOUT = "logout"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    ENROLLMENT_CREATED = "enrollment_created"
    ENROLLMENT_UPDATED = "enrollment_updated"
    GRADE_CHANGE = "grade_change"
    ATTENDANCE_RECORDED = "attendance_recorded"
    DOCUMENT_UPLOADED = "document_uploaded"

    ALL = [
        LOGIN_SUCCESS, LOGIN_FAILED, MFA_FAILED, MFA_ENABLED, MFA_RESET, ACCOUNT_LOCKED,
        LOGOUT, USER_CREATED, USER_UPDATED, ENROLLMENT_CREATED, ENROLLMENT_UPDATED,
        GRADE_CHANGE, ATTENDANCE_RECORDED, DOCUMENT_UPLOADED,
    ]


def record(action: str, *, user_id: int | None, ip: str | None,
           success: bool = True, details: dict | None = None) -> None:
    """Punto único de escritura. Solo IDs en details, nunca datos personales."""
    security.audit_log(action, user_id=user_id, ip=ip, success=success, details=details or {})


_KNOWN = {"_id", "timestamp", "user_id", "action", "ip", "source_ip", "result", "success", "details"}


def list_logs(mongo_db: Database, action: str | None, user_id: int | None,
              page: int = 1, per_page: int = 50) -> tuple[list[dict], bool]:
    """Lista eventos (más recientes primero). Devuelve (filas, hay_más)."""
    query: dict = {}
    # Solo valores simples validados: nunca se pasa un dict del usuario a Mongo
    if action:
        query["action"] = action
    if user_id is not None:
        query["user_id"] = user_id
    cursor = (mongo_db["audit_logs"].find(query)
              .sort("timestamp", -1)
              .skip((page - 1) * per_page)
              .limit(per_page + 1))
    docs = list(cursor)
    rows = []
    for doc in docs[:per_page]:
        result = doc.get("result")
        if result is None and "success" in doc:
            result = "success" if doc["success"] else "failure"
        extra = {k: v for k, v in doc.items() if k not in _KNOWN}
        details = doc.get("details") or {}
        if extra:
            details = {**details, **extra}
        ts = doc.get("timestamp")
        rows.append({
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ts, "strftime") else ts,
            "user_id": doc.get("user_id"),
            "action": doc.get("action"),
            "result": result,
            "ip": doc.get("ip") or doc.get("source_ip"),
            "details": ", ".join(f"{k}={v}" for k, v in details.items()),
        })
    return rows, len(docs) > per_page
