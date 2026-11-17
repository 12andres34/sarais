# SARAIS – Diseño de seguridad

Qué se protege, cómo, y **dónde está la debilidad** de cada control. Datos siempre sintéticos.

---

## 1. Cifrado en tránsito

### 1.1 Navegador → Nginx (HTTPS)

Archivo: `docker/nginx/nginx.conf`. Imagen `nginx-unprivileged` (UID 101), escucha en 8443. La VM publica `443:8443`.

| Elemento | Valor |
|---|---|
| Protocolos | TLS 1.2 y 1.3 (1.0/1.1 rechazados) |
| Cifrados | Solo ECDHE + AES-GCM / ChaCha20 (secreto perfecto hacia adelante) |
| Tickets de sesión | Desactivados (`ssl_session_tickets off`) |
| HSTS | `max-age=31536000`, sin `includeSubDomains` ni `preload` |
| Versión de Nginx | Oculta (`server_tokens off`) |
| Certificado | `scripts/gen_certs.sh` → `docker/nginx/certs/sarais.{crt,key}` (llave `640 root:101`) |

**Quién envía cada cabecera (sin duplicados):**

| Cabecera | La envía | Dónde |
|---|---|---|
| Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Cache-Control | App | `app/main.py` (`SECURITY_HEADERS`) |
| Strict-Transport-Security, Permissions-Policy, Cross-Origin-Opener-Policy | Nginx | `nginx.conf` |

> **Antes** Nginx también enviaba CSP, X-Frame-Options, nosniff y Referrer-Policy. Salían **dos veces**, y la CSP con **valores distintos**. Cuando hay dos CSP, el navegador aplica las dos (la más restrictiva gana), lo que confunde al depurar. Ahora cada cabecera tiene un solo dueño.
>
> **Trampa de Nginx:** un `location` con su propio `add_header` **no hereda** los del `server`. Hoy ningún `location` tiene `add_header`. Si agregas uno, repite las tres cabeceras allí.
>
> **HSTS con certificado autofirmado:** el navegador **ignora** HSTS mientras haya error de certificado. Si importas el certificado en Windows, el host queda forzado a HTTPS por un año. Para borrarlo en Chrome: `chrome://net-internals/#hsts`.

### 1.2 Nginx → App: la IP real en la auditoría

- `proxy_params_sarais` envía `X-Forwarded-For: $remote_addr`. **Reemplaza** lo que mande el cliente. Antes usaba `$proxy_add_x_forwarded_for`, que **agrega** al valor del cliente. Como uvicorn corre con `--forwarded-allow-ips "*"`, un atacante podía escribir la IP que quisiera en `audit_logs`.
- `--forwarded-allow-ips "*"` se mantiene. Es aceptable porque el puerto 8000 de la app **no se publica en la VM**. Solo Nginx llega a él, por la red `frontend`. En desarrollo se publica únicamente en `127.0.0.1`.

### 1.3 App → MySQL (TLS obligatorio)

1. `scripts/gen_mysql_certs.sh` crea una **CA interna** y el certificado del servidor. Vale para los nombres `mysql_db`, `localhost` y `127.0.0.1`. Salida: `docker/mysql/certs/`. La llave de la CA queda en `docker/mysql/ca-private/`, que **no se monta** en ningún contenedor.
2. `docker/mysql/conf.d/sarais.cnf` activa `require_secure_transport=ON` y TLS 1.2/1.3. Desde ese momento, cualquier conexión TCP sin TLS recibe el **error 3159**.
3. El compose monta `ca.pem` en la app y define `MYSQL_SSL_CA`. `app/db.py` ya lo usaba: `connect_args={"ssl": {"ca": ...}}`. PyMySQL, con una CA, **verifica** el certificado **y** el nombre del host (`mysql_db`).
4. El usuario de la app tiene `REQUIRE SSL`. Es una segunda barrera por si alguien apaga `require_secure_transport`.

**Qué pasa con lo que ya existía:**

| Componente | ¿Funciona? | Por qué |
|---|---|---|
| `backup.sh` | Sí | `mysqldump -u$MYSQL_BACKUP_USER` sin `-h` → **socket Unix**. MySQL considera seguro el socket. El usuario `sarais_backup` es `@'localhost'`. |
| `restore.sh` | Sí | `mysql -uroot` por socket |
| Healthcheck (`mysqladmin ping -h 127.0.0.1`) | Sí | El cliente usa TLS solo (`--ssl-mode=PREFERRED` por defecto). Además, `ping` devuelve 0 aunque responda "Access denied". |
| Workbench (desarrollo, `127.0.0.1:3306`) | Sí, con un ajuste | Pestaña **SSL** → *Use SSL* = **Require and Verify CA** → *SSL CA File* = `\\wsl$\Ubuntu-22.04\home\<tú>\<repo>\docker\mysql\certs\ca.pem`. Con *No* → error 3159. |
| `mongo_db` | No aplica | Red `backend` interna (riesgo R15) |

> **Orden obligatorio:** genera los certificados **antes** de `docker compose up`. Si `docker/mysql/certs/` está vacía, MySQL no arranca. En el log aparece un error de SSL.
>
> Si MySQL dice que no puede leer `server-key.pem`: confirma el UID con `docker run --rm sarais/mysql:8.4 id -u` y regenera con `sudo MYSQL_UID=<uid> FORCE=1 ./scripts/gen_mysql_certs.sh`.

---

## 2. Cifrado en reposo

### 2.1 Keyring de MySQL (verificado, no rehecho)

Lo que ya existía, revisado:

| Pieza | Archivo | Estado |
|---|---|---|
| Manifiesto que carga el componente | `docker/mysql/keyring/mysqld.my` → `/usr/sbin/mysqld.my` | ✔ |
| Ruta del keyring | `component_keyring_file.cnf` → `/var/lib/mysql-keyring/component_keyring_file` | ✔ fuera de `/var/lib/mysql` |
| Volumen separado | `mysql_keyring:/var/lib/mysql-keyring` | ✔ sobrevive a recrear el contenedor |
| Permisos | Carpeta `mysql:mysql`. Cambiado de `750` a **`700`** (solo afecta volúmenes nuevos). | ✔ |
| `default_table_encryption`, redo/undo/binlog cifrados | `sarais.cnf` | ✔ ya activos |

Cómo funciona:
- Hay una **llave maestra** en el archivo del keyring.
- Cada tabla tiene su propia llave, guardada **cifrada con la maestra** dentro de su `.ibd`.
- Sin el keyring, los `.ibd` son ilegibles, incluso para MySQL.

`scripts/verify_encryption.sh` lo comprueba todo.

Reglas:
- `docker compose down -v` borra **también** `mysql_keyring`. En desarrollo está bien: se reconstruye desde `ddl.sql` y `dml.sql`. En la VM **nunca** uses `-v`.
- Los backups de `backup.sh` son **lógicos** (`mysqldump`, cifrados luego con GPG). **No dependen del keyring**: se restauran sobre uno nuevo. Por eso no hace falta respaldar el keyring para recuperar datos.

### 2.2 Documentos (GPG, llave pública)

`security.encrypt_document(data)`:

1. Cifra con la llave **pública** `DOCS_GPG_RECIPIENT`. Mejor usar la **huella** de 40 caracteres que el correo: con correo, otra llave con ese mismo correo podría elegirse por error.
2. Guarda `DOCUMENTS_DIR/<uuid>.gpg` con permisos `600` y `O_EXCL` (nunca sobrescribe).
3. Devuelve `documents/<uuid>.gpg`, justo el patrón que exige `document_metadata.storage_path`.

GPG usa `/srv/.gnupg`, que es el `HOME` del usuario `sarais` en la imagen. La app **solo tiene la llave pública**: si alguien la compromete, no puede descifrar los documentos guardados. Para importarla:

```bash
docker cp docs_pub.asc sarais_app:/tmp/ && docker exec sarais_app gpg --import /tmp/docs_pub.asc
```

> La subida de documentos (ruta, formulario y `document_metadata`) sigue pendiente en la app. Ya existen `encrypt_document` y la acción `document_uploaded`.

### 2.3 Secreto MFA (AES-256-GCM)

Columna `users.mfa_secret_encrypted` (`VARBINARY(512)`):

```
[0x01 versión][12 bytes nonce aleatorio][secreto cifrado][16 bytes tag]  = 61 bytes
```

- **GCM** cifra y detecta alteraciones: un byte cambiado → `ValueError`.
- **AAD** `sarais:totp-secret:v1`: el token no sirve en otro contexto.
- El **byte de versión** permite rotar la llave o el algoritmo.
- `APP_TOTP_ENC_KEY` = 32 bytes en base64 (comando en `.env.example`).

**Migración desde el STUB.** El STUB usaba Fernet con la llave derivada por SHA-256. Esos secretos ya **no se leen**. Pasos:

1. Genera una llave **nueva** para `APP_TOTP_ENC_KEY`. No reutilices la anterior para otro algoritmo.
2. Ejecuta el `UPDATE` de abajo **una vez**, como root.
3. Cada usuario registra MFA de nuevo en su siguiente login.

```bash
docker exec mysql_db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$MYSQL_DATABASE" \
  -e "UPDATE users SET mfa_enabled = 0, mfa_secret_encrypted = NULL;"'
```

> **¿Por qué no basta el botón "Reiniciar MFA"?** El admin también tiene MFA con el formato viejo. Con la llave nueva, `verify_second_factor` no puede descifrar su secreto y lo devuelve a `/login`. Nunca llega a `/admin/users`: es un problema del huevo y la gallina.
>
> Si un usuario quedó a medio registro (`mfa_enabled = 0` con un secreto viejo), `get_or_create_setup_secret` ahora genera uno nuevo en lugar de fallar con error 500.

---

## 3. Autenticación

| Control | Implementación |
|---|---|
| Contraseñas | Argon2id, t=3, m=64 MiB, p=4 (perfil RFC 9106), sal de 16 bytes |
| Hash inválido o `ARGON2_HASH_PLACEHOLDER` | `verify_password` → `False`, nunca una excepción |
| MFA | TOTP de 6 dígitos y 30 s, ventana ±1. **Un código solo sirve una vez.** |
| QR | SVG generado en el servidor con `segno` (sin CDN, compatible con la CSP). La página ya va con `Cache-Control: no-store` (`main.py`). |
| Sesión | Cookie firmada, `HttpOnly`, `Secure`, `SameSite=Strict`, cierre por inactividad, regeneración al autenticar |

**Limitación del anti-reutilización:** el último código usado se guarda **en memoria**. Hoy uvicorn corre con un solo proceso, así que funciona. Con varios `--workers`, o tras un reinicio, un código podría servir dos veces dentro de sus 90 s. Un sistema real lo guarda en la BD (columna `last_totp_step`) o en Redis.

### 3.1 Revisión del bloqueo por intentos (`app/services/auth_service.py`)

| Punto | Resultado |
|---|---|
| Contador por usuario en MySQL (`failed_attempts`, `locked_until`) | ✔ |
| `SELECT ... FOR UPDATE` al sumar intentos (sin carreras) | ✔ |
| Se revisa el bloqueo **antes** de verificar la contraseña | ✔ |
| Mismo mensaje para todo fallo (`GENERIC_ERROR`) | ✔ |
| Usuario inexistente: verificación con hash falso (mismo tiempo) | ✔ |
| Cuenta bloqueada o inactiva: mismo tiempo | ⚠ → **corregido**. Antes respondía al instante sin Argon2, y el tiempo revelaba que la cuenta existía. |
| Fallos de MFA suman al contador | ✔ (`register_failure(..., MFA_FAILED)`) |
| Contador a 0 solo tras contraseña **+** MFA | ✔ (`register_success` en `verify_second_factor`) |
| Bloqueo temporal (5 fallos → 15 min) y desbloqueo por admin | ✔ (`MAX_FAILED_ATTEMPTS`, `LOCK_MINUTES`, botón *unlock*) |
| `account_locked` se audita una sola vez | ✔ |
| No lanzar excepciones en `check_password` (perdería el contador por ROLLBACK) | ✔ |

---

## 4. Auditoría

**Problema encontrado:** el validador de `audit_logs` esperaba acciones en MAYÚSCULAS, `source_ip` y `result: 'SUCCESS'`. La app enviaba minúsculas, `ip` y `'success'`. **Mongo rechazaba todos los eventos** (código 121). El STUB solo dejaba un warning en el log: la auditoría no se estaba guardando.

Corrección:
- Validador v2 en `db/mongo/init/01_init_mongo.js` (instalaciones nuevas) y `db/mongo/scripts/migrate_audit_validator.js` (volúmenes existentes).
- Se actualizaron `verify.js` y `audit_logs_crud.js` al formato nuevo.
- `AuditAction` (app) = enum del validador = `AUDIT_ACTIONS` (módulo). Una prueba lo comprueba.
- `details`: números (IDs, `old_score`, `new_score`), booleanos, `null`, y texto **solo** en claves de código (`reason`, `role`, `change`, `status`, `class_date`, `storage_path`) y sin espacios. Además, Mongo prohíbe claves como `name` o `email`.
- `audit_log()` **nunca rompe** la petición: si Mongo falla, escribe `AUDIT_FALLBACK {...}` en el log del contenedor.
- La app solo tiene `insert` y `find` (`saraisAppRole`).

> **Decisión sobre "details solo IDs":** se permiten también **números** porque `grade_change` envía `old_score` y `new_score`. Sin ellos, la auditoría no puede mostrar *qué* cambió. No identifican a nadie por sí solos: el estudiante solo se conoce cruzando `enrollment_id` con MySQL. Si prefieren solo IDs, basta quitar esas dos claves en `teacher_service.py`.

---

## 5. ⚠️ Dónde la llave de cifrado queda débil (y qué haría un sistema real)

| Llave | Dónde vive | Por qué es débil | Sistema real |
|---|---|---|---|
| **Llave maestra de MySQL** | Volumen `mysql_keyring`, **en el mismo disco** que los datos | Quien tenga root en la VM, el `.vdi` o un snapshot de VirtualBox tiene **datos y llave juntos**. Solo protege contra el robo del volumen de datos **sin** el keyring. | KMS/HSM (Vault, AWS KMS: requiere MySQL Enterprise) o **LUKS** en el disco de la VM con clave al arrancar |
| **`APP_TOTP_ENC_KEY`**, **`APP_SECRET_KEY`** | `.env` en texto plano y **variables de entorno** del contenedor | Dump de MySQL + `.env` = todos los secretos MFA. `docker inspect sarais_app` las muestra a todo el grupo `docker`. Sin rotación. | Docker secrets (`/run/secrets`) o Vault. Rotación (el byte de versión lo permite). |
| **Llave privada GPG** (backups y documentos) | Fuera de la VM (operador) | Si se pierde, todo es irrecuperable (R10). Si queda en la VM, el cifrado no sirve. | Token de hardware (YubiKey) + copia offline en caja fuerte |
| **CA de MySQL** (`ca-key.pem`) | `docker/mysql/ca-private/` en la VM | Con ella se emite un certificado falso de `mysql_db` | Generarla fuera de línea; en el servidor solo `ca.pem` |
| **Certificado de Nginx** | Autofirmado | Los usuarios se acostumbran a ignorar la advertencia (MITM) | Certificado de una CA reconocida |

**Para la sustentación:** el cifrado en reposo de SARAIS protege contra el **robo de copias y medios**, no contra un **administrador comprometido**.
