# SARAIS – Análisis de riesgos

Alineado con **ISO/IEC 27001:2022**: la cláusula 6.1.2 (valoración de riesgos) y 6.1.3 (tratamiento), con los controles del **Anexo A** (numeración 2022). Alcance: aplicación SARAIS, sus bases de datos, la VM Ubuntu Server y los procesos de backup. Caso de estudio: un colegio privado pequeño. Datos sintéticos.

## 1. Metodología

**Riesgo = Impacto × Probabilidad** (escala 1–5 cada uno).

| Valor | Impacto | Probabilidad |
|---|---|---|
| 1 | Insignificante: sin datos personales | Rara: no se espera en años |
| 2 | Menor: dato interno, se corrige fácil | Improbable |
| 3 | Moderado: datos de pocos estudiantes, días sin servicio | Posible: una vez al año |
| 4 | Mayor: datos de menores expuestos o notas alteradas | Probable |
| 5 | Grave: fuga masiva, pérdida total, sanción de la SIC | Casi segura |

| Riesgo | Nivel | Tratamiento |
|---|---|---|
| 1–5 | Bajo | Aceptar y vigilar |
| 6–11 | Medio | Mitigar cuando sea razonable |
| 12–19 | Alto | Mitigar obligatoriamente |
| 20–25 | Crítico | Mitigar de inmediato o no operar |

**Riesgo inherente:** sin controles. **Riesgo residual:** con los controles **ya implementados** en SARAIS.

## 2. Activos de información

| ID | Activo | Tipo | C | I | D | Dónde |
|---|---|---|---|---|---|---|
| A1 | Datos personales de estudiantes (menores) y acudientes | Información | 5 | 4 | 3 | MySQL |
| A2 | Notas y asistencia | Información | 4 | 5 | 4 | MySQL |
| A3 | Credenciales: hashes Argon2 y secretos MFA cifrados | Información | 5 | 4 | 3 | MySQL |
| A4 | Registro de auditoría | Información | 3 | 5 | 3 | MongoDB `audit_logs` |
| A5 | Documentos de estudiantes (`.gpg`) y sus metadatos | Información | 5 | 4 | 3 | Volumen `app_documents` + MongoDB `document_metadata` |
| A6 | Backups cifrados | Información | 5 | 4 | 5 | `backups/` en la VM |
| A7 | Llave maestra de MySQL (keyring) | Llave | 5 | 5 | 5 | Volumen `mysql_keyring` |
| A8 | Llave privada GPG | Llave | 5 | 5 | 5 | Fuera de la VM (operador) |
| A9 | Secretos de la app (`.env`: `APP_SECRET_KEY`, `APP_TOTP_ENC_KEY`, contraseñas BD) | Llave | 5 | 4 | 4 | `.env` en la VM |
| A10 | Llaves TLS (Nginx, MySQL, CA interna) | Llave | 4 | 4 | 3 | `certs/` |
| A11 | VM Ubuntu Server + Docker | Infraestructura | 4 | 5 | 5 | VirtualBox |
| A12 | Código fuente y configuración | Software | 2 | 5 | 3 | Git |
| A13 | Servicio web (disponibilidad) | Servicio | – | – | 4 | Nginx + app |

C = confidencialidad, I = integridad, D = disponibilidad (1–5).

## 3. Matriz de riesgos

I = impacto, P = probabilidad, R = riesgo. "Inh." = inherente, "Res." = residual.

| ID | Activo | Amenaza | Vulnerabilidad | I | P | R inh. | Controles implementados (Anexo A) | I | P | R res. |
|---|---|---|---|---|---|---|---|---|---|---|
| **R1** | A3, A13 | Fuerza bruta / relleno de credenciales | Login expuesto en la red | 4 | 4 | **16** Alto | Argon2id; bloqueo por intentos en BD; `limit_req` 5/min en Nginx; MFA TOTP; mismo mensaje de error y `dummy_verify` (A.8.5, A.5.17) | 4 | 1 | **4** Bajo |
| **R2** | A1, A2 | Inyección SQL | Consultas con datos del usuario | 5 | 3 | **15** Alto | Consultas parametrizadas (`text()` con `:parámetros` de SQLAlchemy); usuario MySQL sin `DELETE`/DDL (A.8.28, A.8.2) | 4 | 1 | **4** Bajo |
| **R3** | A3 | XSS / robo de sesión | Plantillas HTML con datos | 4 | 3 | **12** Alto | Autoescape de Jinja2; CSP sin `unsafe-inline`; token CSRF en todos los POST; cookies `HttpOnly`, `Secure`, `SameSite` (A.8.28) | 4 | 1 | **4** Bajo |
| **R4** | A2 | Docente o estudiante accede a datos ajenos (IDOR) | IDs en URLs | 4 | 3 | **12** Alto | Matriz rol × recurso; filtro por dueño en el servidor; pruebas por rol (A.5.15, A.8.3) | 4 | 2 | **8** Medio |
| **R5** | A2, A4 | Alteración de notas sin rastro | Usuarios con permiso de escritura | 5 | 3 | **15** Alto | Solo el docente asignado cambia notas; `grade_change` en auditoría solo-agregar (A.8.15, A.5.3) | 5 | 1 | **5** Bajo |
| **R6** | A1, A3 | Intercepción en la red (MITM) | Tráfico HTTP / app↔MySQL en claro (en la primera versión, MySQL aceptaba TCP sin TLS) | 5 | 3 | **15** Alto | TLS 1.2/1.3 en Nginx; HSTS; `require_secure_transport` y CA verificada en MySQL (A.8.24, A.8.20) | 5 | 2 | **10** Medio¹ |
| **R7** | A1, A6 | Robo de un backup o de un disco/volumen | Copias fuera del servidor | 5 | 3 | **15** Alto | Backups cifrados con GPG + SHA-256; tablespaces, redo/undo y binlog cifrados (A.8.24, A.8.13, A.7.10) | 5 | 1 | **5** Bajo |
| **R8** | A3 | Robo de la base → secretos MFA | Secretos guardados | 5 | 2 | **10** Medio | AES-256-GCM con llave fuera de la BD (A.8.24) | 5 | 1 | **5** Bajo² |
| **R9** | A7 | **Pérdida del keyring de MySQL** | Llave en un solo archivo; `down -v` o recrear el contenedor sin montaje | 5 | 3 | **15** Alto | Keyring en volumen separado y verificado (`verify_encryption.sh`); backups **lógicos** que no dependen del keyring; prueba de restauración hecha (A.8.13, A.5.30) | 4 | 1 | **4** Bajo |
| **R10** | A8, A6, A5 | **Pérdida de la llave privada GPG** | Única llave para descifrar backups y documentos | 5 | 2 | **10** Medio | Llave fuera de la VM; **dos copias** (USB + papel) en lugares distintos; prueba de descifrado periódica (A.8.13, A.8.24) | 5 | 1 | **5** Bajo |
| **R11** | A11 y todos | **Usuario del grupo `docker` = root** | `sarais_admin` y `sarais_ops` están en `docker`; `docker run -v /:/host`; `docker inspect` muestra secretos | 5 | 3 | **15** Alto | Solo 2 usuarios en `docker`, auditor fuera; SSH solo con llaves y sin root (`harden_ssh.sh`); `check_permissions.sh` lista los miembros (A.8.2, A.8.18) | 5 | 2 | **10** Medio³ |
| **R12** | A4 | **Root manipula o borra la auditoría** | Root del host o root de Mongo pueden hacer `deleteMany` | 5 | 2 | **10** Medio | La app no puede borrar (rol sin `remove`); respaldo de eventos en `docker logs` (`AUDIT_FALLBACK`); `mongodump` en backups cifrados; el rol root de Mongo solo se usa para migraciones (A.8.15, A.5.28) | 5 | 2 | **10** Medio⁴ |
| **R13** | A9 | **`.env` expuesto en Git** | Commit accidental; líneas del `.gitignore` con espacios al inicio que no ignoraban nada (corregido) | 5 | 3 | **15** Alto | `.env` en `.gitignore` y sacado del índice (`git rm --cached`); `.env.example` sin valores; `check_permissions.sh` lo verifica; contraseñas **distintas** en la VM (A.8.4, A.5.17) | 5 | 1 | **5** Bajo⁵ |
| **R14** | A9 | Secretos leídos desde el host | `.env` en texto plano; variables de entorno visibles | 5 | 2 | **10** Medio | `.env` en `600`; mínimos usuarios con acceso a la VM (A.5.17, A.8.2) | 5 | 2 | **10** Medio⁶ |
| **R15** | A4, A5 | Sniffing dentro de la red de Docker | App ↔ Mongo sin TLS | 3 | 1 | **3** Bajo | Red interna de Docker; Mongo sin puerto publicado en la VM; Mongo sin datos personales (A.8.22) | 3 | 1 | **3** Bajo (aceptado) |
| **R16** | A13, A11 | Ransomware / falla de disco | VM única | 5 | 3 | **15** Alto | Backups cifrados diarios por cron; restauración probada; copia fuera de la VM (A.8.13, A.8.14) | 4 | 2 | **8** Medio |
| **R17** | A11 | Imágenes Docker con vulnerabilidades (CVE) | Versiones sin parchear | 4 | 3 | **12** Alto | Imágenes oficiales y ligeras; usuario no root; `HEALTHCHECK`; actualizar con `docker compose pull` (A.8.8) | 4 | 2 | **8** Medio |
| **R18** | A1 | Datos personales en logs o auditoría | Programadores registran demasiado | 4 | 3 | **12** Alto | `details` solo IDs (validado en Python **y** en Mongo); sin datos personales en Mongo (A.8.11, A.5.34) | 4 | 1 | **4** Bajo |
| **R19** | A1 | Uso de datos reales en desarrollo | Copia de la base de producción | 5 | 2 | **10** Medio | Solo datos sintéticos (`dml.sql`) (A.8.33, A.5.34) | 5 | 1 | **5** Bajo |
| **R20** | A3 | Reutilización de un código MFA visto por otro | Código válido 30–90 s | 3 | 2 | **6** Medio | Cada código sirve **una sola vez** (`verify_totp`) (A.8.5) | 3 | 1 | **3** Bajo⁷ |
| **R22** | A4 | Eventos de auditoría perdidos | Esquema del validador distinto al de la app (MAYÚSCULAS/`source_ip`) — **hallado en esta revisión** | 4 | 5 | **20** Crítico | Validador v2 alineado; prueba que compara `AuditAction.ALL` con el enum; respaldo `AUDIT_FALLBACK` en el log (A.8.15) | 4 | 1 | **4** Bajo |
| **R23** | A4 | IP falsificada en la auditoría | Nginx agregaba (`$proxy_add_x_forwarded_for`) la IP enviada por el cliente y uvicorn confía en todo (`*`) — **hallado en esta revisión** | 3 | 3 | **9** Medio | Nginx reemplaza la cabecera con `$remote_addr`; el puerto de la app no se publica en la VM (A.8.15, A.8.20) | 3 | 1 | **3** Bajo |
| **R21** | A13 | Denegación de servicio | Un solo servidor | 3 | 2 | **6** Medio | `limit_req`; límite de subida (10 MB en la app, 11 MB en Nginx, 413 antes de leer el cuerpo); `restart: unless-stopped` (A.8.6) | 3 | 2 | **6** Medio (aceptado) |
| **R24** | A13, A11 | **VM sin servicio por conflicto Hyper-V / AVX** (hallado en el despliegue) | El mismo PC usa WSL2/Docker Desktop (Hyper-V encendido) y VirtualBox. Con Hyper-V activo la CPU virtual no tiene AVX y MongoDB 7 no arranca → sin auditoría, sin documentos, la app no inicia. Cambiar Hyper-V puede pedir la llave de recuperación de BitLocker | 3 | 4 | **12** Alto | Regla escrita: Hyper-V **apagado** para la VM (`bcdedit /set hypervisorlaunchtype off`), **encendido** para WSL (`auto`); revisar BitLocker antes; `preflight.sh` falla si no hay AVX; cambios de código en una sola tanda con Hyper-V encendido y una sola actualización de la VM (A.5.30, A.8.9) | 3 | 2 | **6** Medio⁸ |
| **R25** | A3, A4 | **Cambio de contraseñas fuera de la app, sin auditoría** (hallado en el despliegue) | Quien está en el grupo `docker` puede usar `docker exec` y escribir en `users` directo (se hizo un rehash de todas las cuentas cuando se olvidó la contraseña demo). Ese cambio no pasa por la app → no queda evento en `audit_logs` | 4 | 3 | **12** Alto | Solo 2 usuarios en `docker` (R11); SSH con llaves; `app/scripts/reset_password.py` restablece contraseñas **con** evento `user_updated` (`change=password_reset_cli`); regla: todo otro cambio manual se anota en una bitácora con fecha, quién y por qué (A.5.18, A.8.15, A.8.2) | 4 | 2 | **8** Medio⁹ |
| **R26** | A5, A11 | Archivo malicioso subido como "PDF" | La subida acepta archivos de docentes y admin | 3 | 2 | **6** Medio | Solo admin/docente; CSRF; extensión `.pdf` + firma `%PDF-` + `%%EOF`; tamaño máximo; el archivo **nunca se abre ni se interpreta** en el servidor, se cifra al instante; nombre UUID (sin rutas del usuario) (A.8.28, A.8.7) | 3 | 1 | **3** Bajo¹⁰ |

### Notas del riesgo residual

1. **R6:** el certificado de Nginx es autofirmado. Si el usuario acepta una advertencia falsa, un atacante en la misma red podría interceptar. Solución real: un certificado de una CA reconocida.
2. **R8:** si el atacante roba **la base y además** el `.env`, descifra todo. La llave está en el mismo servidor (ver `security_design.md` §5).
3. **R11:** es inherente a Docker. `sarais_ops` está en `docker` porque `backup.sh` usa `docker exec`: **riesgo aceptado**. Mitigación real: `sudo` limitado a `backup.sh` en lugar del grupo `docker`, Docker *rootless* o Podman, y `auditd`.
4. **R12:** no se puede eliminar con lo que tenemos. Quien tenga root manda. Mitigación real: enviar los eventos, en el momento, a un servidor externo de solo-agregar (syslog remoto o SIEM), o firmar cada evento en cadena con hashes. **Riesgo aceptado** y documentado.
5. **R13:** si `.env` alguna vez estuvo en un commit, **sigue en el historial**. Hay que **cambiar todas las contraseñas y llaves**; borrarlo del índice no basta. En la VM se usan valores distintos a los de desarrollo.
6. **R14:** se reduciría con Docker secrets o un gestor de secretos (Vault).
7. **R20:** el registro de códigos usados vive en memoria (ver `security_design.md` §3).
8. **R24:** es un riesgo del entorno académico (un solo PC para desarrollar y para la VM). En producción real el servidor sería una máquina o VM dedicada, sin Hyper-V compartido. Otra opción: MongoDB 4.4 (no exige AVX), descartada por estar fuera de soporte.
9. **R25:** no se elimina mientras root o el grupo `docker` existan (igual que R11 y R12). Mitigación real: un *trigger* de MySQL en `users` que copie cada cambio de `password_hash` a una tabla de historial (registra también lo que haga root), o un `auditd` que registre cada `docker exec`.
10. **R26:** la app no abre los PDF, pero **quien los descifre** fuera del servidor sí. Mitigación real: antivirus (ClamAV) antes de cifrar y abrir los PDF descifrados en un visor aislado.

## 4. Riesgos más altos después de los controles (plan)

| Riesgo | Residual | Acción propuesta (fuera de alcance académico) |
|---|---|---|
| R6 | 10 | Certificado de una CA reconocida |
| R11 | 10 | Docker rootless; `auditd` |
| R12 | 10 | Envío de auditoría a un sistema externo; hashes encadenados |
| R14 | 10 | Docker secrets o Vault; rotación de llaves |
| R4, R16, R17 | 8 | Pruebas automáticas por rol; segunda copia de backup fuera del sitio; escaneo de imágenes (Trivy) |
| R25 | 8 | Trigger de historial en `users`; `auditd` sobre `docker exec` |
| R24 | 6 | Servidor dedicado (sin Hyper-V compartido) |

## 5. Declaración de aplicabilidad (resumen)

| Control (Anexo A 2022) | ¿Aplica? | Implementación en SARAIS |
|---|---|---|
| 5.15 Control de acceso | Sí | Matriz rol × recurso (`access_control.md`) |
| 5.17 Información de autenticación | Sí | Argon2id; `.env` fuera de Git |
| 5.34 Privacidad y protección de PII | Sí | Ley 1581 (`docs/legal/`); datos solo en MySQL |
| 8.2 Derechos de acceso privilegiado | Sí | Usuario MySQL sin DDL; grupo docker controlado |
| 8.5 Autenticación segura | Sí | MFA TOTP; bloqueo por intentos |
| 8.13 Respaldo de información | Sí | `backup.sh` + GPG + SHA-256; restauración probada |
| 8.15 Registro (logging) | Sí | `audit_logs` solo-agregar |
| 8.20 Seguridad de redes | Sí | TLS; UFW; puertos de BD no expuestos |
| 8.24 Uso de criptografía | Sí | TLS, tablespaces, AES-GCM, GPG |
| 8.28 Codificación segura | Sí | Consultas parametrizadas, autoescape, CSP |
| 7.x Seguridad física | No | VM académica; fuera de alcance |
