# SARAIS · Aplicación (FastAPI + Jinja2)

## Estructura
```
app/
├── main.py            # crea la app: sesión, cabeceras, errores, routers
├── config.py          # variables de entorno
├── db.py              # MySQL (SQLAlchemy+PyMySQL) y MongoDB (pymongo)
├── deps.py            # autorización: get_current_user, require_role
├── web.py             # plantillas, CSRF, flash, validación
├── security/          # Argon2id, TOTP (anti-reutilización + QR), AES-GCM, GPG, auditoría
├── models/forms.py    # modelos Pydantic de los formularios
├── services/          # lógica + SQL parametrizado (auth, user, enrollment, teacher, student, document, audit)
├── routers/           # rutas: auth, admin, teacher, student, documents, pages
├── templates/         # HTML Jinja2 (sin JS ni estilos en línea)
├── static/css/        # CSS local
├── scripts/seed_data.py
└── tests/             # pytest (sin bases de datos reales)
```

## Ejecutar
```bash
docker compose up -d --build
docker compose exec -e SEED_PASSWORD='UnaClaveDemoLarga2026' app python -m app.scripts.seed_data
# abrir http://127.0.0.1:8000  (o https://localhost con Nginx)
```

## Pruebas (en WSL, desde la raíz del repo)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r app/requirements-dev.txt
pytest app/tests -q
```

## Rutas
| Rol | Rutas |
|---|---|
| Todos | `/login`, `/login/mfa`, `/login/mfa/setup`, `/logout` (POST), `/health` |
| admin | `/admin`, `/admin/users`, `/admin/enrollments`, `/admin/audit` |
| teacher | `/teacher`, `/teacher/assignments/{id}/grades`, `/teacher/assignments/{id}/attendance` |
| student | `/student` (boletín), `/student/attendance` |
| admin y teacher | `/documents` (lista y subida de PDF cifrados con GPG) |
