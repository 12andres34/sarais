"""Validación con Pydantic, reglas de configuración y protección del stub."""
from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.config import load_settings, today_local
from app.models.forms import (AttendanceEntry, ClassDateForm, GradeEntry, MfaCodeForm,
                              UserCreateForm)
from app.services.teacher_service import parse_grade_form

BASE_ENV = {
    "SECRET_KEY": "x" * 40, "MYSQL_DATABASE": "d", "MYSQL_USER": "u",
    "MYSQL_PASSWORD": "p", "MONGO_URI": "mongodb://h/db",
}


# ----------------------------- Notas -----------------------------
@pytest.mark.parametrize("value, expected", [("4.5", Decimal("4.5")), ("4,5", Decimal("4.5")),
                                             ("0", Decimal("0")), ("5.00", Decimal("5.00"))])
def test_grade_valid(value, expected):
    assert GradeEntry(score=value).score == expected


@pytest.mark.parametrize("value", ["5.01", "-1", "abc", "4.555", "10"])
def test_grade_invalid(value):
    with pytest.raises(ValidationError):
        GradeEntry(score=value)


def test_observation_too_long():
    with pytest.raises(ValidationError):
        GradeEntry(score="4", observation="a" * 256)


def test_parse_grade_form_ignores_foreign_ids_and_blanks():
    roster = [{"enrollment_id": 1, "student_name": "A"}, {"enrollment_id": 2, "student_name": "B"}]
    data = {"score_1": "4,5", "score_2": "", "score_999": "5"}  # 999 no es del curso
    entries, errors = parse_grade_form(roster, data)
    assert errors == []
    assert list(entries) == [1]
    assert entries[1].score == Decimal("4.5")


def test_parse_grade_form_reports_errors():
    roster = [{"enrollment_id": 1, "student_name": "Pérez Ana"}]
    entries, errors = parse_grade_form(roster, {"score_1": "7"})
    assert entries == {}
    assert "Pérez Ana" in errors[0]


# ------------------------- Otros formularios -------------------------
def test_attendance_status_must_be_known():
    assert AttendanceEntry(status="absent").status == "absent"
    with pytest.raises(ValidationError):
        AttendanceEntry(status="sick")


def test_class_date_cannot_be_future():
    with pytest.raises(ValidationError):
        ClassDateForm(class_date=today_local() + timedelta(days=1))


def test_mfa_code_six_digits():
    assert MfaCodeForm(code=" 123456 ").code == "123456"
    for bad in ["12345", "1234567", "12a456"]:
        with pytest.raises(ValidationError):
            MfaCodeForm(code=bad)


def test_user_create_rules():
    ok = dict(username="ana.perez", email="ana@sarais.test", password="x" * 12)
    assert UserCreateForm(**ok, role="student", student_id="3").student_id == 3
    with pytest.raises(ValidationError):  # estudiante sin vínculo
        UserCreateForm(**ok, role="student", student_id="")
    with pytest.raises(ValidationError):  # contraseña corta
        UserCreateForm(**{**ok, "password": "corta"}, role="admin")
    with pytest.raises(ValidationError):  # rol inexistente
        UserCreateForm(**ok, role="root")
    with pytest.raises(ValidationError):  # caracteres no permitidos
        UserCreateForm(**{**ok, "username": "ana<script>"}, role="admin")


# --------------------------- Configuración ---------------------------
def test_cookie_secure_by_default_and_production_default():
    s = load_settings(dict(BASE_ENV))
    assert s.cookie_secure is True
    assert s.is_production  # sin APP_ENV se asume producción


def test_production_rejects_insecure_cookie():
    with pytest.raises(RuntimeError):
        load_settings({**BASE_ENV, "APP_ENV": "production", "COOKIE_SECURE": "false"})


def test_short_secret_key_rejected():
    with pytest.raises(RuntimeError):
        load_settings({**BASE_ENV, "SECRET_KEY": "corta"})


def test_missing_variable_rejected():
    env = dict(BASE_ENV)
    del env["MYSQL_PASSWORD"]
    with pytest.raises(RuntimeError):
        load_settings(env)


def test_stub_blocks_production(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "get_settings", lambda: load_settings(dict(BASE_ENV)))
    monkeypatch.setattr(main.security, "IS_STUB", True, raising=False)
    with pytest.raises(RuntimeError):
        main.create_app()
