# SARAIS – Solución de problemas y lecciones aprendidas

Problemas reales encontrados al desplegar y probar SARAIS en la VM, con su causa y la solución aplicada.
Varios se convirtieron en controles (`preflight.sh`, `check_permissions.sh`, `reset_password.py`) o en riesgos de la matriz (`docs/risk_analysis.md`: R13, R24, R25).

## Despliegue inicial (19–20 nov 2026)

| Problema | Causa | Solución aplicada |
|---|---|---|
| `ping 192.168.56.10` falla y `enp0s8` sin IP | La IP fija no quedó en el instalador | En la consola: `sudo netplan set "ethernets.enp0s8.addresses=[192.168.56.10/24]"`, `sudo netplan set ethernets.enp0s8.dhcp4=false`, `sudo netplan apply` |
| `grep avx` vacío y tortuga verde en VirtualBox | Hyper-V (WSL2/Docker Desktop) esconde AVX; MongoDB 7 lo exige | Actualizar VirtualBox o `bcdedit /set hypervisorlaunchtype off` + reiniciar (revisar BitLocker antes). Para volver a WSL: `... auto` + reiniciar |
| La página deja de cargar tras volver a encender | Hyper-V se activó de nuevo → sin AVX → `mongo_db` cae → la app y Nginx no arrancan | Apagar Hyper-V antes de usar la VM |
| SSH pide `password:` después de la frase de paso | La llave no llegó a `authorized_keys` (Ubuntu vacía `/tmp` al reiniciar) | Reenviar la `.pub` y repetir `setup_users.sh /tmp/keys` |
| `Enter passphrase for key` con una llave antigua | Ya existía `~/.ssh/id_ed25519` con frase de paso | Usar esa frase o crear `~/.ssh/id_sarais` + `~/.ssh/config` |
| `preflight.sh`: `ca.pem` con grupo `1001` | La carpeta tiene setgid y hereda el grupo `sarais` | `sudo chown root:root` a los dos `.pem` públicos (corregido en `gen_mysql_certs.sh`) |
| `syntax error near unexpected token 'newline'` | Un `<` de más pegado al final del comando | Revisar el final de la línea antes de Enter |
| Contraseña demo olvidada | Solo se guarda su hash Argon2 (es de una sola vía) | `docker compose exec -e NEW_PASSWORD app python -m app.scripts.reset_password --all` (hash por cuenta + evento `user_updated`, control de R25). Volver a correr `seed_data` **no** sirve: solo reemplaza hashes pendientes |
| El usuario de instalación no es `sysadmin` | Se creó como `admin-sarais` | Donde la guía dice `sysadmin`, usar el usuario real |

## Actualización, pruebas y métricas (23–25 nov 2026)

| Problema | Causa | Solución aplicada |
|---|---|---|
| "No se pudo guardar el documento" (`storage_error`) | `DOCS_GPG_RECIPIENT` seguía con el valor de ejemplo `sarais-docs@example.local` | Importar `docs_pub.asc` en `sarais_app`; poner la **huella** en `.env` (`sed -i "s/^DOCS_GPG_RECIPIENT=.*/DOCS_GPG_RECIPIENT=$FPR/" .env`); `docker compose up -d app` |
| gpg intentaba buscar la llave en Internet ("via WKD") | Comportamiento por defecto de gpg cuando falta la llave | `crypto.py` usa `--auto-key-locate clear,local` (solo llavero local) |
| El cambio en `.env` o en el código no se aplica | `docker compose restart` no relee `.env` ni reconstruye la imagen | `docker compose up -d --build app` |
| Disco de la VM al 92 % (`ALERT:DISK`) | Cada `--build` deja imágenes y caché viejas | Después de cada build: `docker image prune -f && docker builder prune -f`. **Nunca** `--volumes` |
| `sudo vgs: command not found` | La VM no usa LVM: `/` es `/dev/sda3` (24 GB) | No hace falta agrandar; basta con el `prune` |
| `check_permissions.sh`: scripts en `775` y `ca-private` en `2700` | `git pull` crea archivos con el umask `002` de `sarais_ops`; la carpeta hereda setgid | `sudo ./scripts/check_permissions.sh --fix`, `sudo chmod g-s docker/mysql/ca-private`; `umask 027` en `~/.profile` de `sarais_ops`; correr `check_permissions.sh` tras cada `pull` |
| `Permission denied (publickey)` con `sarais_ops` o `sarais_auditor` desde Windows | La llave de Windows solo estaba en `authorized_keys` de `sarais_admin` | Copiar la `.pub` con `scp` y agregarla como `sarais_admin` con `install -d -m 700` + `tee -a` + `chmod 600` |
| `Connection reset ... [preauth]` | `ssh ... \| Select-String` escondía la pregunta de la frase de paso | Conectar sin filtros; opcional `ssh-agent` + `ssh-add` |
| `sudo` pide contraseña de `sarais_ops` | `sarais_ops` no tiene contraseña ni `sudo` (mínimo privilegio) | `preflight.sh` y `check_permissions.sh` se corren como `sarais_admin` |
| `./scripts/backup.sh: No such file or directory` | Se ejecutó desde `~`, no desde `/opt/sarais` | `cd /opt/sarais` antes de cualquier script (o `echo 'cd /opt/sarais' >> ~/.profile`) |
| Un `.env.bak` casi se sube a GitHub | `.gitignore` solo ignoraba `.env` exacto | Agregar `.env.*` y `!.env.example`; revisar `git status` antes de cada commit |
| PC recalentado con la VM 24 h encendida | Carga sostenida en un portátil | Métricas por escenarios cortos; apagar con `sudo shutdown -h now`, nunca suspender ni "Apagar la máquina" en VirtualBox |
| Tras el restore en WSL no se puede entrar a la app | Los secretos MFA vienen cifrados con `APP_TOTP_ENC_KEY` de la VM | Es lo esperado: la evidencia se toma con SQL. Para volver a usar WSL: `down -v`, `up -d`, `chmod 600` del keyring, importar `docs_pub.asc`, `seed_data` |
