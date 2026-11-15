"""Autorización en el servidor: cada rol solo entra a lo suyo."""
import pytest

from app.tests.conftest import FakeDB, extract_csrf


@pytest.mark.parametrize("role, url", [
    ("student", "/admin"),
    ("student", "/admin/users"),
    ("student", "/admin/audit"),
    ("student", "/teacher"),
    ("teacher", "/admin"),
    ("teacher", "/admin/enrollments"),
    ("teacher", "/student"),
    ("admin", "/teacher"),
    ("admin", "/student/attendance"),
])
def test_role_cannot_open_other_role_pages(client, fake_db, login_as, role, url):
    login_as(role, teacher_id=1, student_id=1)
    response = client.get(url)
    assert response.status_code == 403
    assert "Acceso denegado" in response.text


def test_teacher_cannot_open_assignment_of_other_teacher(client, fake_db, login_as):
    login_as("teacher", teacher_id=7)
    response = client.get("/teacher/assignments/123/grades")
    assert response.status_code == 403
    # La consulta exige que la asignación sea del docente de la SESIÓN
    sql, params = fake_db.calls[0]
    assert "ta.teacher_id = :tid" in sql
    assert params == {"aid": 123, "tid": 7}


def test_teacher_cannot_post_grades_to_other_group(client, fake_db, login_as):
    login_as("teacher", teacher_id=7)
    token = extract_csrf(client.get("/login").text)  # crea la sesión con token CSRF
    response = client.post("/teacher/assignments/123/grades",
                           data={"csrf_token": token, "period_id": "1", "score_5": "5.0"})
    assert response.status_code == 403
    assert not any("INSERT" in sql or "UPDATE" in sql for sql, _ in fake_db.calls)


def test_teacher_post_without_csrf_is_rejected(client, fake_db, login_as):
    login_as("teacher", teacher_id=7)
    response = client.post("/teacher/assignments/1/grades", data={"period_id": "1"})
    assert response.status_code == 403
    assert fake_db.calls == []  # se rechaza antes de tocar la base de datos


def test_teacher_account_not_linked(client, fake_db, login_as):
    login_as("teacher", teacher_id=None)
    assert client.get("/teacher").status_code == 403


def test_student_only_sees_own_report_card(client, fake_db, login_as):
    login_as("student", student_id=42)
    # Aunque alguien agregue ?student_id=1 a la URL, se usa el de la sesión
    response = client.get("/student?student_id=1")
    assert response.status_code == 200
    sql, params = fake_db.calls[0]
    assert "v_report_card" in sql
    assert params["sid"] == 42


def test_student_account_not_linked(client, fake_db, login_as):
    login_as("student", student_id=None)
    assert client.get("/student").status_code == 403


def test_admin_cannot_create_user_without_csrf(client, fake_db, login_as):
    login_as("admin")
    response = client.post("/admin/users", data={"username": "nuevo", "role": "admin"})
    assert response.status_code == 403
    assert isinstance(fake_db, FakeDB) and fake_db.calls == []
