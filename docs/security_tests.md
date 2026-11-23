# SARAIS – Pruebas de seguridad

Cada prueba indica el **comando** y el **resultado esperado**. Guarda una captura de cada una como evidencia para el informe.
Host: `localhost` en desarrollo (con Nginx: `sudo ./scripts/gen_certs.sh localhost`) o `192.168.56.10` en la VM.

## 0. Pruebas automáticas

| # | Prueba | Comando | Esperado |
|---|---|---|---|
| 0.1 | Toda la app + módulo de seguridad | `pip install -r app/requirements-dev.txt && pytest app/tests -q` | Todo PASS (2 skip de integración) |
| 0.2 | Cifrado y TLS de MySQL | `./scripts/verify_encryption.sh` | `0 FAIL` |
| 0.3 | Validador de auditoría | `migrate_audit_validator.js` (comando en su cabecera) | 3 `PASS aceptado` y 5 `PASS rechazado (121)` |
| 0.4 | Mongo con el usuario de la app | `verify.js` (comando en `db/mongo/README.md`) | `RESULTADO: todas las pruebas PASS` |
| 0.5 | Permisos | `./scripts/check_permissions.sh` | `Problemas: 0` |

## 1. TLS en Nginx

| # | Prueba | Comando | Esperado |
|---|---|---|---|
| 1.1 | TLS 1.1 rechazado | `openssl s_client -connect localhost:443 -tls1_1 </dev/null` | Falla el handshake¹ |
| 1.2 | TLS 1.2 aceptado | `openssl s_client -connect localhost:443 -tls1_2 </dev/null 2>/dev/null \| grep -E "Protocol\|Cipher"` | `TLSv1.2`, cifrado `ECDHE-...-GCM-...` |
| 1.3 | TLS 1.3 aceptado | ídem con `-tls1_3` | `TLSv1.3` |
| 1.4 | Cifrado sin PFS rechazado | `openssl s_client -connect localhost:443 -tls1_2 -cipher AES128-GCM-SHA256 </dev/null` | Falla el handshake |
| 1.5 | Puerto 80 cerrado | `curl -m 3 http://localhost` | `Connection refused` (solo se publica 443) |
| 1.6 | Cabeceras | `curl -skI https://localhost/login` | `strict-transport-security`, `content-security-policy`, `x-frame-options`, `x-content-type-options`, `referrer-policy`, `permissions-policy`; `server: nginx` **sin versión** |
| 1.7 | Sin duplicados | `curl -skI https://localhost/login \| cut -d: -f1 \| tr A-Z a-z \| sort \| uniq -d` | Vacío (`set-cookie` repetido es normal) |
| 1.8 | Una sola CSP | `curl -skI https://localhost/login \| grep -ci content-security-policy` | `1` |

¹ El OpenSSL de Ubuntu 22.04 puede negarse **por su cuenta** a usar TLS 1.1. Para probar el servidor, agrega `-cipher 'DEFAULT@SECLEVEL=0'`. `s_client` mostrará `self-signed certificate`: es lo esperado.

## 2. TLS en MySQL

| # | Prueba | Comando | Esperado |
|---|---|---|---|
| 2.1 | Sin TLS rechazado | `docker exec -it mysql_db sh -c 'mysql -u"$MYSQL_APP_USER" -p -h127.0.0.1 --ssl-mode=DISABLED'` | `ERROR 3159 ... insecure transport are prohibited` |
| 2.2 | TLS verificado | `docker exec -it mysql_db sh -c 'mysql -u"$MYSQL_APP_USER" -p -h127.0.0.1 --ssl-mode=VERIFY_IDENTITY --ssl-ca=/etc/mysql/certs/ca.pem -e "SHOW SESSION STATUS LIKE \"Ssl_version\""'` | `TLSv1.3` |
| 2.3 | La app usa TLS | Haz login en la app y ejecuta como root: `SELECT PROCESSLIST_USER, CONNECTION_TYPE FROM performance_schema.threads WHERE PROCESSLIST_USER IS NOT NULL;` | `sarais_app` → `SSL/TLS` |
| 2.4 | El usuario exige TLS | `SELECT user, ssl_type FROM mysql.user WHERE user='sarais_app';` | `ANY` |
| 2.5 | Sin DELETE ni DDL | Como `sarais_app`: `DELETE FROM grades;` y `DROP TABLE grades;` | Error `1142` en ambos |
| 2.6 | Backup sigue funcionando | `./scripts/backup.sh` | Termina sin error y crea un `.gpg` nuevo |
| 2.7 | Healthcheck | `docker inspect -f '{{.State.Health.Status}}' mysql_db` | `healthy` |
| 2.8 | Workbench | `127.0.0.1:3306`, SSL = *Require and Verify CA* con `ca.pem` | Conecta. Con SSL = *No* → error 3159. |

## 3. Cifrado en reposo

| # | Prueba | Comando | Esperado |
|---|---|---|---|
| 3.1 | Tablas cifradas | `SELECT NAME, ENCRYPTION FROM information_schema.INNODB_TABLESPACES WHERE NAME LIKE 'sarais/%';` | 13 filas con `Y` |
| 3.2 | Tabla nueva cifrada por defecto | Como root: `CREATE TABLE sarais.t_enc (id INT); SELECT CREATE_OPTIONS FROM information_schema.TABLES WHERE TABLE_NAME='t_enc'; DROP TABLE sarais.t_enc;` | `ENCRYPTION='Y'` sin haberlo escrito |
| 3.3 | El `.ibd` no tiene texto legible | 1) Copia un apellido sintético de `students`. 2) `docker exec mysql_db grep -c "<Apellido>" /var/lib/mysql/sarais/students.ibd` | `0` |
| 3.4 | Secreto MFA cifrado | `SELECT username, LENGTH(mfa_secret_encrypted), HEX(LEFT(mfa_secret_encrypted,1)) FROM users WHERE mfa_secret_encrypted IS NOT NULL;` | Largo `61`, primer byte `01` |
| 3.5 | Documento cifrado | Sube un PDF sintético en `/documents`. Luego `docker exec sarais_app sh -c 'ls -l /srv/data/documents'` | Archivos `-rw-------` con nombre UUID `.gpg` |
| 3.5b | El `.gpg` no tiene el PDF en claro | `docker exec sarais_app sh -c 'head -c 5 /srv/data/documents/*.gpg \| od -c \| head -3'` | No aparece `% P D F -` |
| 3.5c | Metadatos sin datos personales | `docker exec mongo_db sh -c 'mongosh -u "$MONGO_APP_USER" -p "$MONGO_APP_PASSWORD" --authenticationDatabase sarais sarais --quiet --eval "db.document_metadata.find().sort({upload_date:-1}).limit(1)"'` | Solo `type`, `upload_date`, `uploader_id`, `student_ref`, `storage_path` |
| 3.5d | Rechazo de un archivo falso | Renombra un `.txt` a `.pdf` y súbelo | Aviso "no es un PDF válido"; en `/admin/audit`, `document_uploaded` Fallo con `reason=not_pdf` |
| 3.6 | La app no puede descifrar | `docker exec sarais_app gpg --list-secret-keys` | Vacío: solo hay llave pública |

## 4. Roles y permisos

Usuarios de `dml.sql` con la `SEED_PASSWORD`.

| # | Rol | Acción | Esperado |
|---|---|---|---|
| 4.1 | Sin sesión | Abrir `/admin/users` | Redirección a `/login` |
| 4.2 | student | Abrir `/admin/users` y `/teacher` | `403` |
| 4.3 | teacher | Abrir `/admin/users` y `/student` | `403` |
| 4.4 | teacher | Abrir `/teacher/assignments/<ID de otro docente>/grades` | `403` o `404`, sin datos |
| 4.5 | teacher | Guardar notas en su asignación | OK y evento `grade_change` con `old_score` y `new_score` |
| 4.6 | admin | Abrir `/teacher` (cambiar notas) | `403` (separación de funciones) |
| 4.7 | admin | Crear usuario | OK y `user_created` |
| 4.8 | Cualquiera | Enviar un POST sin `csrf_token` | `403 Token CSRF inválido` |
| 4.9 | Mongo (`sarais_app`) | `db.audit_logs.deleteOne({})` | Error `13` |

## 5. MFA

| # | Prueba | Esperado |
|---|---|---|
| 5.1 | `/login/mfa/setup` muestra el QR. En F12 → Red, ninguna petición va a otro dominio. | QR visible, solo peticiones a `localhost` |
| 5.2 | Cabecera de esa página | `Cache-Control: no-store` |
| 5.3 | Escanear el QR y escribir el código | Entra. Eventos `mfa_enabled` y `login_success` |
| 5.4 | Código incorrecto | `Código incorrecto`. Evento `mfa_failed` |
| 5.5 | **Mismo código dos veces:** cierra sesión y entra de nuevo antes de 30 s con el mismo código | El segundo se rechaza (`mfa_failed`) |
| 5.6 | Admin → "Reiniciar MFA" a un usuario | Evento `mfa_reset`; ese usuario vuelve a ver el QR |
| 5.7 | Cambiar `APP_TOTP_ENC_KEY` sin reiniciar MFA | Ese usuario vuelve a `/login` (sin error 500). Solución: `UPDATE` de `security_design.md` §2.3 |

## 6. Bloqueo por intentos

| # | Prueba | Esperado |
|---|---|---|
| 6.1 | 5 contraseñas incorrectas seguidas | Cuenta bloqueada. Un solo evento `account_locked` (`minutes: 15`). |
| 6.2 | Contraseña **correcta** estando bloqueada | Mismo mensaje genérico. `login_failed` con `reason: locked`. |
| 6.3 | Usuario inexistente vs. bloqueado vs. contraseña mala | Mismo mensaje y tiempo parecido: `curl -sk -o /dev/null -w "%{time_total}\n" ...` |
| 6.4 | Más de 5 POST a `/login` en 1 minuto desde la misma IP | Nginx responde `503` (valor por defecto de `limit_req`) |
| 6.5 | 5 códigos MFA errados | `account_locked` |
| 6.6 | Admin → "Desbloquear" | Entra de nuevo. `user_updated` con `change: unlock` |

## 7. Auditoría

```bash
docker exec -it mongo_db sh -c 'mongosh -u "$MONGO_APP_USER" -p "$MONGO_APP_PASSWORD" \
  --authenticationDatabase "$MONGO_INITDB_DATABASE" "$MONGO_INITDB_DATABASE" --quiet \
  --eval "db.audit_logs.find({}, {_id:0}).sort({timestamp:-1}).limit(10).forEach(printjson)"'
```

También en la app: `/admin/audit`.

| # | Prueba | Esperado |
|---|---|---|
| 7.1 | Eventos de las secciones 4–6 | Uno por acción, `result` = `success`/`failure` |
| 7.2 | IP real | `ip` es la del navegador, **no** la de Nginx (172.x) |
| 7.3 | IP falsificada: `curl -sk -H "X-Forwarded-For: 1.2.3.4" -d "username=x&password=y" https://localhost/login` | El evento **no** tiene `1.2.3.4` |
| 7.4 | Sin datos personales en `details` | Solo números y códigos |
| 7.5 | Usuario inexistente | `user_id: null`, `reason: unknown_user` |
| 7.6 | Mongo caído: `docker stop mongo_db` y luego login | La app funciona y `docker logs sarais_app \| grep AUDIT_FALLBACK` muestra el evento. Después: `docker start mongo_db`. |

## 8. Secretos y contenedores

| # | Prueba | Comando | Esperado |
|---|---|---|---|
| 8.1 | `.env` fuera de Git | `git ls-files .env` | Vacío |
| 8.2 | `.env` nunca en el historial | `git log --all --oneline -- .env` | Vacío. Si no: **cambiar todos los secretos** (R13). |
| 8.3 | Llaves ignoradas | `git check-ignore -v docker/mysql/certs/server-key.pem docker/nginx/certs/sarais.key` | Las dos aparecen |
| 8.4 | Secretos visibles para el grupo docker | `docker inspect sarais_app --format '{{range .Config.Env}}{{println .}}{{end}}' \| grep -c KEY` | Mayor a 0. Es la **evidencia del riesgo R11/R14**, no un error de la prueba. |
| 8.5 | Contenedores sin root | `docker exec sarais_app id` · `docker exec mysql_db id` · `docker exec sarais_nginx id` | UID 10001 · 999 · 101 |
