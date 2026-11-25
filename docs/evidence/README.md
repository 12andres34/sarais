# Evidencias de las pruebas (VM, 24–25 nov 2026)

Capturas tomadas en la VM `adminsarais-VirtualBox` (192.168.56.10), salvo las marcadas como WSL o Windows.
Nombre de archivo = columna *Archivo* + `.png`. Cada captura muestra `whoami; date` para identificar quién ejecutó la prueba y cuándo.
Ninguna muestra contraseñas, el contenido de `.env`, el QR de MFA ni llaves privadas.

Referencias: pruebas de infraestructura (`INF-n`, `docs/infrastructure_guide.md` §5) y de seguridad (`SEC-n`, `docs/security_tests.md`). Riesgos (`Rn`, `docs/risk_analysis.md`).

## Infraestructura Linux y Docker

| Archivo | Dónde / usuario | Qué demuestra | Prueba | Riesgo |
|---|---|---|---|---|
| E1 | Windows (VirtualBox) | VM con 2 vCPU, 4 GB, NAT + solo-anfitrión | — | — |
| E2 | VM · sarais_admin | IP fija `192.168.56.10/24` y reloj sincronizado | — | — |
| E3 | VM · sarais_ops | Docker Engine y Compose instalados | — | — |
| E4 | VM · sarais_admin | Usuarios, grupos y permisos de carpetas (mínimo privilegio) | — | R11, R14 |
| E5 | VM · sarais_admin | `sshd -T`: sin root, sin contraseña, solo llave | INF-19 | R1 |
| E5B | Windows · PowerShell | `ssh root` y `ssh` sin llave → `Permission denied (publickey)` | INF-17, INF-18 | R1 |
| E6 | VM · sarais_admin | UFW: deny incoming, 22 LIMIT, 443 ALLOW | INF-20 | R1, R21 |
| E7 | VM · sarais_ops | `.env` válido y con permisos `600` | SEC-8 | R13, R14 |
| E8 | VM · sarais_ops | GPG: solo llaves públicas en `sarais_ops` y en la app | SEC-3.6 | R7, R10 |
| E9 | VM · sarais_admin | `preflight.sh` → 0 FAIL (incluye AVX y llave de documentos) | — | R24 |
| E10E11 | VM · sarais_ops | Los 4 servicios `healthy` y contenedores sin root (UID 10001, 999, 999, 101) | INF-1, INF-2, SEC-8.5 | R17, R21 |
| E12 | VM · sarais_admin | Solo escuchan 22 y 443; no 3306 ni 27017 | INF-3 | R1 |
| E12B | Windows · PowerShell | 443 abierto; 3306, 27017 y 80 cerrados desde fuera | INF-4, SEC-1.5 | R1 |

## Cifrado y bases de datos

| Archivo | Dónde / usuario | Qué demuestra | Prueba | Riesgo |
|---|---|---|---|---|
| E13 | VM · sarais_ops | `verify_encryption.sh` → 16 PASS, 0 FAIL | SEC-0.2 | R6, R7 |
| E14 | VM · sarais_ops | 13 tablas con `ENCRYPTION = Y`; el apellido no aparece en el `.ibd` | INF-7, SEC-3.1, SEC-3.3 | R7 |
| E15 | VM · sarais_ops | Sin TLS → rechazo (1045, `REQUIRE SSL`); con TLS → `TLSv1.3`; la app usa `SSL/TLS` | SEC-2.1 a 2.3 | R6, R15 |
| E16 | VM · sarais_ops | La cuenta de la app no puede `DELETE` ni `DROP` (1142) | INF-8, SEC-2.5 | R2, R5 |
| E26 | VM · sarais_ops | La app no puede borrar la auditoría en Mongo (error 13) | SEC-4.9 | R5, R22 |
| E34 | VM · sarais_ops | Los secretos son visibles para el grupo `docker` (riesgo aceptado) | SEC-8.4 | R11, R14 |
| E35 | VM · sarais_ops | Documentos `.gpg` con nombre UUID, `600`, sin PDF en claro; la app sin llave privada | SEC-3.5, 3.5b, 3.6 | R7, R10 |
| E36 | VM · sarais_ops | `document_metadata` solo con IDs y códigos | SEC-3.5c | R18 |
| E38 | WSL | `pytest`: 111 passed, 1 skipped | SEC-0.1 | R2, R3, R4 |
| E39 | WSL | `.env` y llaves fuera de Git; `.env` en el historial (secretos rotados) | SEC-8.1 a 8.3 | R13 |
| E40 | VM · sarais_admin | `check_permissions.sh` → solo queda el hallazgo del historial (R13) | SEC-0.5 | R13, R14 |

## TLS de la aplicación

| Archivo | Dónde / usuario | Qué demuestra | Prueba | Riesgo |
|---|---|---|---|---|
| E17 | VM · sarais_ops | TLS 1.1 rechazado; TLS 1.2 y 1.3 aceptados con ECDHE + AES-GCM | SEC-1.1 a 1.3 | R6 |
| E18 | VM · sarais_ops | Cabeceras HSTS, una sola CSP, XFO, nosniff; `server: nginx` sin versión | SEC-1.6 a 1.8 | R3 |
| E19 | Navegador | Certificado autofirmado con `CN = 192.168.56.10` | INF-5 | R6 |
| E20 | Navegador | Página del QR: todas las peticiones a `192.168.56.10` (QR tapado) | SEC-5.1 | R8 |

## Autenticación, roles y auditoría

| Archivo | Dónde / usuario | Qué demuestra | Prueba | Riesgo |
|---|---|---|---|---|
| E21 | Navegador | MFA: código incorrecto y código reutilizado → rechazados | SEC-5.4, 5.5 | R1, R20 |
| E22A, E22B | Navegador | E22A: 403 del estudiante. E22B: 403 del docente (RBAC) | SEC-4.2, 4.3 | R4 |
| E23 | Navegador | Bloqueo tras 5 intentos con mensaje genérico | SEC-6.1, 6.2 | R1 |
| E24 | VM · sarais_ops | Nginx responde `503` al pasar el límite de logins | SEC-6.4 | R1, R21 |
| E25 | Navegador | `/admin/audit`: eventos con IP real y sin datos personales | SEC-7.1, 7.2, 7.4 | R18, R23 |
| E33 | VM · sarais_auditor | El auditor lee el log, pero no usa Docker ni lee `.env` | INF-21 | R11, R12 |
| E37A, E37B | Navegador | E37A: PDF válido cifrado. E37B: archivo falso rechazado (`not_pdf`) | SEC-3.5d | R26 |

## Backups, restauración y monitoreo

| Archivo | Dónde / usuario | Qué demuestra | Prueba | Riesgo |
|---|---|---|---|---|
| E27 | VM · sarais_ops | Backup cifrado: `PGP RSA encrypted`, `0` líneas legibles | INF-9, INF-10 | R7 |
| E27B | VM · sarais_ops | Backup posterior al cambio de prueba (nota 4.7): tiempo y tamaño | INF-9 | R16 |
| E28, E28B | WSL | E28: restauración en entorno limpio. E28B: aparece la nota 4.70 de la VM | INF-11 | R16 |
| E29 | WSL | Backup alterado en 1 byte → `El checksum NO coincide`; no se restaura | INF-12 | R16 |
| E30 | VM · sarais_ops | Cron de backup, monitor y limpieza; CSV con filas recientes | INF-16 | R16, R21 |
| E31A, E31B | VM y WSL | E31A: tabla de métricas por escenario (VM). E31B: gráfica `docs/img/vm_metrics.png` | — | — |
| E32 | VM · sarais_ops | Alertas reales del 23-nov: `ALERT:CPU`, `ALERT:mongo`, `ALERT:DISK` | INF-14 | R21, R24 |

## Escenarios de métricas (25-nov-2026, muestreo cada minuto)

| Escenario | Ventana | Actividad |
|---|---|---|
| Reposo | 09:45 – 10:15 | Sistema encendido, sin usuarios |
| Uso | 10:21 – 10:36 | Logins con MFA, notas, asistencia, subida de PDF, auditoría |
| Backup | 10:38 | `backup.sh` con documentos (≈20 MB) |

Tablas: `docs/img/metrics_idle.md`, `docs/img/metrics_usage.md`. Figuras: `docs/img/vm_metrics*.png`.
Reproducir: `python3 scripts/metrics_report.py metrics_2026-11.csv --since 2026-11-25T09:45 --until 2026-11-25T10:15`.
