# SARAIS · Secure and Reliable Academic Information System

Sistema web seguro de gestión académica para una institución educativa pequeña: usuarios, matrículas, notas, asistencia, boletín, documentos cifrados y auditoría.

Proyecto integrador de tercer semestre de Ingeniería de Datos e IA. Integra **Bases de Datos**, **Sistemas Operativos** y **Seguridad de la Información**.

> **Solo datos sintéticos.** Ningún dato de este repositorio corresponde a personas reales.

---

## 1. Qué hace cada rol

| Rol | Puede |
|---|---|
| **Administrador** (directivo) | Crear y activar/desactivar usuarios, desbloquear cuentas, reiniciar MFA, gestionar matrículas, subir documentos de cualquier tipo, consultar la auditoría |
| **Docente** | Ver sus grupos, registrar notas y asistencia (solo sus asignaciones y periodos abiertos), subir excusas y otros documentos de **sus** estudiantes |
| **Estudiante** | Ver su boletín y su asistencia |
| Acudiente | Sin cuenta en esta versión (trabajo futuro, ver `docs/access_control.md` §5) |

Todos entran con usuario, contraseña y **MFA** (código TOTP en el celular).

## 2. Arquitectura

```
 Navegador ──HTTPS 443──▶ nginx (TLS 1.2/1.3, HSTS, límite de login y de subida)
                             │  red "frontend"
                             ▼
                         app  (FastAPI + Jinja2, usuario no root)
                          │    │          │
               TLS (CA)   │    │          └─▶ volumen app_documents  (PDF cifrados .gpg)
                          ▼    ▼              volumen app_gnupg      (solo llave PÚBLICA)
                    mysql_db   mongo_db
             (13 tablas 3FN,   (audit_logs solo-agregar,
            tablespaces        document_metadata)
              cifrados)
                  red "backend" (interna: sin salida ni puertos publicados en la VM)
```

| Servicio | Imagen | Función |
|---|---|---|
| `nginx` | `sarais/nginx:1.0` | Proxy inverso con TLS. Único puerto publicado: 443 |
| `app` | `sarais/app:1.0` | Aplicación web, autenticación, autorización, cifrado |
| `mysql_db` | `sarais/mysql:8.4` | Datos académicos y personales |
| `mongo_db` | `sarais/mongo:7.0` | Auditoría y metadatos de documentos (sin datos personales) |

## 3. Tecnologías

| Área | Herramientas |
|---|---|
| Bases de datos | MySQL 8.4 (relacional, 3FN, vista de boletín) · MongoDB 7 (JSON Schema, rol de mínimo privilegio) |
| Aplicación | Python 3.12, FastAPI, Jinja2, SQLAlchemy (consultas parametrizadas), Pydantic |
| Seguridad | Argon2id, TOTP (pyotp), AES-256-GCM, GPG, TLS (OpenSSL), CSRF, CSP, RBAC, auditoría |
| Infraestructura | Ubuntu Server 22.04 (VirtualBox), Docker + Compose, Bash + cron, UFW, SSH con llaves |
| Desarrollo | Windows + WSL2 (Ubuntu 22.04), Docker Desktop, VS Code, pytest |

## 4. Estructura del repositorio

```
.
├── app/                    # Aplicación FastAPI (ver app/README.md)
│   ├── routers/            #   rutas por rol: auth, admin, teacher, student, documents
│   ├── services/           #   lógica + SQL parametrizado
│   ├── security/           #   Argon2, TOTP, AES-GCM, GPG, auditoría
│   ├── templates/ static/  #   HTML sin JavaScript ni estilos en línea
│   └── tests/              #   pytest (sin bases de datos reales)
├── db/
│   ├── ddl.sql             # 13 tablas, llaves, CHECK, índices, vista v_report_card
│   ├── dml.sql             # datos sintéticos
│   ├── queries.sql         # JOIN, subconsultas, GROUP BY, HAVING
│   └── mongo/              # init (validadores, índices, rol), scripts CRUD
├── docker/                 # Un Dockerfile por servicio + configuración (nginx, mysql, mongo, app)
├── scripts/                # Bash: backup, restore, monitor, cleanup, certificados, preflight...
│   └── linux/              #   usuarios y grupos, SSH, UFW
├── docs/                   # Diseño, seguridad, riesgos, despliegue (ver §9)
├── docker-compose.yaml           # producción (VM)
├── docker-compose.override.yaml  # solo desarrollo (puertos en 127.0.0.1)
└── .env.example            # plantilla de variables. El .env real NUNCA va a Git
```

## 5. Inicio rápido en desarrollo (WSL2)

Requisitos: WSL2 con Ubuntu 22.04, Docker Desktop con integración WSL, `gpg` y `openssl`.

```bash
# 1. Variables de entorno (secretos nuevos y aleatorios)
cp .env.example .env            # y cambia TODOS los valores (o usa ./scripts/gen_env.sh)

# 2. Certificados ANTES del primer "up" (si faltan, Docker crea carpetas en su lugar)
sudo ./scripts/gen_mysql_certs.sh
sudo ./scripts/gen_certs.sh localhost

# 3. Levantar
docker compose up -d --build
docker compose ps               # los 4 servicios en "healthy"

# 4. Llave PÚBLICA de documentos dentro de la app (una sola vez; queda en el volumen app_gnupg)
docker exec -i sarais_app gpg --batch --import < ~/sarais_keys/docs_pub.asc
#    y en .env: DOCS_GPG_RECIPIENT=<huella de 40 caracteres>  →  docker compose up -d app

# 5. Usuarios de demostración
read -rs -p "Contraseña demo: " SEED_PASSWORD; echo; export SEED_PASSWORD
docker compose exec -e SEED_PASSWORD app python -m app.scripts.seed_data
unset SEED_PASSWORD
```

Abrir `https://localhost` (Nginx) o `http://127.0.0.1:8000` (app directa, solo desarrollo).

## 6. Pruebas

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r app/requirements-dev.txt
pytest app/tests -q
```

No necesitan MySQL ni MongoDB: usan dobles falsos. Las pruebas de GPG crean una llave temporal (se saltan si `gpg` no está instalado). Las pruebas de seguridad sobre el sistema desplegado están en `docs/security_tests.md`.

## 7. Despliegue en la VM

Guía completa, paso a paso: **`docs/deployment_walkthrough.md`**. Referencia técnica: `docs/deployment_vm.md`. Solución de problemas: `docs/troubleshooting.md`.

Resumen del flujo: `git push` en WSL → en la VM `git pull` → `sudo ./scripts/preflight.sh` (0 FAIL) → `docker compose up -d --build`.

Reglas que no se rompen:
- **Nunca** `docker compose down -v` en la VM: borra las bases y el keyring de MySQL.
- La llave **privada** GPG nunca entra a la VM ni a GitHub.
- Hyper-V **apagado** en Windows para usar la VM (MongoDB 7 necesita AVX). Ver riesgo R24.

### Tareas programadas (cron de `sarais_ops`)

| Script | Cuándo | Qué hace |
|---|---|---|
| `backup.sh` | Diario 2:00 | `mysqldump` + `mongodump` + documentos → `.tar.gz.gpg` + `.sha256` |
| `monitor.sh` | Cada 5 min | CPU, RAM, disco y contenedores → CSV; alerta si supera el umbral |
| `cleanup.sh` | Domingo 3:30 | Borra backups, logs y métricas viejos según la retención |

Otros: `restore.sh`, `verify_encryption.sh`, `check_permissions.sh`, `metrics_report.py` (métricas por escenario: reposo, uso, backup) y `app/scripts/reset_password.py` (restablece contraseñas dejando evento en la auditoría).

## 8. Seguridad (resumen)

| Control | Implementación |
|---|---|
| Autenticación | Argon2id + MFA TOTP (secreto cifrado con AES-256-GCM, código de un solo uso) |
| Bloqueo | 5 intentos fallidos → 15 min; `limit_req` en Nginx para `/login` |
| Autorización | RBAC (admin/teacher/student) aplicado en el servidor; filtro por dueño contra IDOR |
| Cifrado en tránsito | TLS en Nginx; TLS verificado app → MySQL (`require_secure_transport`) |
| Cifrado en reposo | Tablespaces de MySQL cifrados (keyring); documentos y backups con GPG |
| Aplicación web | CSRF en todo POST, CSP sin `unsafe-inline`, autoescape, cookies `HttpOnly`/`Secure`/`SameSite=Strict` |
| Auditoría | `audit_logs` solo-agregar (la app no puede editar ni borrar), sin datos personales |
| Mínimo privilegio | Usuario MySQL sin `DELETE` ni DDL; rol de Mongo a medida; contenedores no root con `cap_drop: ALL` |
| Credenciales | Solo en `.env` (`600`, fuera de Git) |

## 9. Documentación

| Archivo | Contenido |
|---|---|
| `docs/data_dictionary.md` | Modelo entidad-relación y diccionario de datos |
| `docs/normalization_3nf.md` | Normalización hasta 3FN |
| `docs/mongodb_justification.md` | Por qué y para qué MongoDB |
| `docs/security_design.md` | Diseño de seguridad y manejo de llaves |
| `docs/access_control.md` | Matriz rol × recurso, cuentas de BD y de Linux, permisos |
| `docs/risk_analysis.md` | Activos, amenazas, matriz de riesgos (ISO/IEC 27001:2022) |
| `docs/security_tests.md` | Pruebas de seguridad y evidencias |
| `docs/infrastructure_guide.md` | Docker, red, volúmenes, scripts |
| `docs/deployment_walkthrough.md` · `docs/deployment_vm.md` | Despliegue en la VM (guía detallada y referencia técnica) |
| `docs/troubleshooting.md` | Problemas reales del despliegue y su solución |
| `docs/legal/` | Ley 1581 de 2012 y consentimiento informado |
| `docs/evidence/` | Capturas de las pruebas con su índice (`README.md`) |
| `docs/img/` | Tablas y gráficas de métricas |
