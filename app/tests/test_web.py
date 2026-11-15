"""Pruebas de la capa web: health, sesión, CSRF, cabeceras y páginas de error."""
from app.tests.conftest import extract_csrf


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_login_page_has_csrf_and_secure_cookie_flags(client):
    response = client.get("/login")
    assert response.status_code == 200
    extract_csrf(response.text)
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie


def test_security_headers(client):
    response = client.get("/login")
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"


def test_anonymous_is_redirected_to_login(client):
    for url in ["/", "/admin", "/teacher", "/student"]:
        response = client.get(url, follow_redirects=False)
        assert response.status_code == 303, url
        assert response.headers["location"] == "/login"


def test_post_without_csrf_is_rejected(client, fake_db):
    response = client.post("/login", data={"username": "x", "password": "y"})
    assert response.status_code == 403
    assert "CSRF" in response.text


def test_post_with_wrong_csrf_is_rejected(client, fake_db):
    client.get("/login")
    response = client.post("/login", data={"username": "x", "password": "y", "csrf_token": "falso"})
    assert response.status_code == 403


def test_unknown_user_gets_generic_error_and_is_audited(client, fake_db, audit_calls):
    token = extract_csrf(client.get("/login").text)
    response = client.post("/login", data={"username": "nadie", "password": "x", "csrf_token": token})
    assert response.status_code == 401
    assert "Usuario o contraseña incorrectos" in response.text
    assert audit_calls[0][0] == "login_failed"
    assert audit_calls[0][1]["user_id"] is None
    # La consulta usa parámetros, no concatena el texto del usuario
    sql, params = fake_db.calls[0]
    assert ":username" in sql and params == {"username": "nadie"}


def test_sql_injection_attempt_is_just_data(client, fake_db, audit_calls):
    token = extract_csrf(client.get("/login").text)
    payload = "admin' OR '1'='1"
    client.post("/login", data={"username": payload, "password": "x", "csrf_token": token})
    sql, params = fake_db.calls[0]
    assert payload not in sql
    assert params["username"] == payload


def test_mfa_page_requires_password_step(client, fake_db):
    response = client.get("/login/mfa", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_404_shows_clean_error_page(client):
    response = client.get("/no-existe")
    assert response.status_code == 404
    assert "Página no encontrada" in response.text
    assert "Traceback" not in response.text


def test_docs_are_disabled(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
