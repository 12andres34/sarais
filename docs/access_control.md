# SARAIS – Control de acceso

Principio: **mínimo privilegio**. Cada persona, cuenta de servicio y archivo tiene solo el acceso que necesita.

## 1. Matriz rol × recurso (aplicación)

C = crear · R = leer · U = actualizar · — = sin acceso. **Nadie borra desde la app**: se desactiva o se cambia de estado. Por eso el usuario MySQL no tiene `DELETE`.

| Recurso | admin | teacher | student | Dónde se aplica |
|---|---|---|---|---|
| `users` (crear, activar/desactivar, desbloquear, reiniciar MFA) | C R U | — | — | `ADMIN` en `routers/admin.py` |
| Su propio login y MFA | ✔ | ✔ | ✔ | `routers/auth.py` |
| `enrollments` | C R U (estado) | — | — | `/admin/enrollments` |
| `audit_logs` | R | — | — | `/admin/audit` |
| `teaching_assignments` | — | R (solo las suyas) | — | `teacher_service.get_owned_assignment` |
| `grades` | — | C R U (sus asignaciones y periodo abierto) | R (las suyas, en el boletín) | `teacher_service` / `student_service` |
| `attendance` | — | C R U (sus asignaciones, periodo abierto) | R (la suya) | ídem |
| Vista `v_report_card` (boletín) | — | — | R (el suyo) | `/student` |
| `students`, `guardians`, `subjects`, `class_groups`, `periods` | Carga por `dml.sql`/`seed_data.py` (sin pantallas) | R (sus estudiantes, en listas) | R (sus datos) | — |
| Documentos (`document_metadata` + `.gpg`) | Pendiente en la app | Pendiente | — | `encrypt_document` listo |

**Decisiones:**

- **Control por objeto, en el servidor.** El docente no ve "todas las notas". Cada consulta filtra por el `teacher_id` **de la sesión**, nunca por uno que venga del formulario (`teacher_service.py`, línea 2). El estudiante usa su `student_id` de la sesión. Si alguien cambia el ID en la URL, recibe 403/404, nunca datos ajenos. Este ataque se llama IDOR. Lo prueba `app/tests/test_authorization.py`.
- **Separación de funciones.** El admin **no** cambia notas; solo el docente asignado. Cada cambio de nota tiene un responsable claro en `audit_logs` (`grade_change`).
- **Acudientes:** hoy no tienen cuenta (decisión pendiente). Si se agregan, sería un rol `guardian` de solo lectura sobre los estudiantes vinculados en `student_guardians`.

## 2. Cuentas de bases de datos

### MySQL

| Cuenta | Desde | Privilegios | Uso |
|---|---|---|---|
| `root` | Socket dentro del contenedor (`docker exec`) | Todos | Init, `restore.sh`, scripts de verificación |
| `sarais_app` (`MYSQL_APP_USER`) | Red Docker (`'%'`) | `SELECT, INSERT, UPDATE` en `sarais`, **`REQUIRE SSL`** | La app y Workbench |
| `sarais_backup` (`MYSQL_BACKUP_USER`) | Solo `'localhost'` (socket) | `SELECT, SHOW VIEW, TRIGGER, EVENT, LOCK TABLES`, `SHOW_ROUTINE` | `backup.sh` |

Lo crea `docker/mysql/init/05_users.sh` (primera vez). Para un volumen ya creado se usa `scripts/apply_mysql_grants.sh`.

| Necesidad de la app | Privilegio |
|---|---|
| Leer tablas y la vista `v_report_card` | `SELECT`. La vista es `SQL SECURITY DEFINER` por defecto: basta con `SELECT` sobre ella. |
| Crear usuarios, matrículas, notas, asistencia | `INSERT` |
| Editar, contar intentos, bloquear | `UPDATE` |
| `SELECT ... FOR UPDATE` (en `register_failure`) | MySQL exige `SELECT` + (`UPDATE`, `DELETE` o `LOCK TABLES`). Con `UPDATE` alcanza. |
| `DELETE` | **Quitado.** Antes estaba concedido sin necesidad: la app no ejecuta ningún `DELETE`. |
| DDL (`CREATE`, `DROP`, `ALTER`) | No. `DROP` → error 1142. |

**Opcional para la VM:** `MYSQL_ROOT_HOST=localhost` en `.env` **antes del primer arranque**. Así root solo entra por socket, nunca por la red.

### MongoDB

| Cuenta | Privilegios |
|---|---|
| root (`MONGO_INITDB_ROOT_USERNAME`) | Todo. Solo para init y `migrate_audit_validator.js`. |
| `sarais_app` (rol `saraisAppRole`) | `audit_logs`: `find`, `insert` (**sin** update/remove/collMod) · `document_metadata`: CRUD |

## 3. Usuarios de Linux en la VM (`scripts/linux/setup_users.sh`)

| Usuario | Grupos | Para qué |
|---|---|---|
| `sarais_admin` | sudo, docker, sarais | Administra el servidor |
| `sarais_ops` | docker, sarais, sarais-ops | Despliega, cron, backups |
| `sarais_auditor` | sarais, sarais-audit | Solo lee logs y métricas |

### Grupo `docker` = root

Quien está en `docker` puede ejecutar `docker run -v /:/host ...` y leer **todo** el disco. También puede ver los secretos con `docker inspect`. `sarais_admin` y `sarais_ops` están en él: `sarais_ops` lo necesita porque `backup.sh` usa `docker exec`.

**Riesgo aceptado (R11).** Mitigaciones:
- SSH solo con llaves (`harden_ssh.sh`).
- `sarais_auditor` **fuera** de `docker`.
- Lista de miembros revisada con `check_permissions.sh`.

Alternativa real: que `sarais_ops` **no** esté en `docker`, y que cron ejecute `backup.sh` con `sudo` limitado a ese único script en `sudoers`.

## 4. Permisos de archivos

Los revisa `scripts/check_permissions.sh` (`--fix` corrige solo con `chmod`).

| Ruta | Modo | Dueño | Motivo |
|---|---|---|---|
| `.env` | `600` | `sarais_ops` | Contraseñas y llaves. Fuera de Git. |
| `docker/nginx/certs/sarais.key` | `640` | `root:101` | Nginx corre como UID 101 (`gen_certs.sh`) |
| `docker/mysql/certs/server-key.pem` | `600` | UID 999 (`mysql`) | `gen_mysql_certs.sh` |
| `docker/mysql/certs/ca.pem`, `server-cert.pem` | `644` | root | Públicos |
| `docker/mysql/ca-private/` | `700` / `600` | root | Puede emitir certificados. No se monta. |
| Volumen `mysql_keyring` | `700` | `mysql` | Llave maestra de MySQL |
| Volumen `app_documents` | archivos `600` | `sarais` (10001) | Documentos `.gpg` |
| `/srv/.gnupg` (en la imagen) | `700` | `sarais` | **Solo la llave pública** |
| `/var/backups/sarais` | `700` / archivos `640` | `sarais_ops` | Backups `.gpg` + `.sha256` |
| `/var/log/sarais` | `2750` | `sarais_ops:sarais-audit` | El auditor lee, no escribe |

### `.gitignore` corregido

Las líneas `   .env`, `   backups/` y `   certs/` tenían **espacios al inicio**. Git las trata como otro patrón, así que **no ignoraban nada**. `.env` sí quedaba ignorado gracias a otra línea sin espacios; `certs/` no. Ahora además se ignoran `*-key.pem`, `docker/mysql/certs/*` y `docker/mysql/ca-private/`.
