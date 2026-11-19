# SARAIS – Despliegue en la VM (paso a paso, en orden)

Guía para desplegar SARAIS en la VM Ubuntu Server 22.04. Sigue los pasos **en orden**: cada uno tiene un **"Compruébalo"**. Si un "Compruébalo" falla, no sigas: revisa la sección 11 (problemas comunes).

- `WSL$` = terminal Ubuntu de WSL2 en tu PC (`~/proyecto_integrador`).
- `PS>` = PowerShell de Windows.
- `VM$` = terminal de la VM. El usuario va indicado: `VM(admin)$`, `VM(ops)$`, `VM(auditor)$`.
- **Siempre** trabaja desde la raíz del repo (`/opt/sarais` en la VM). Los scripts usan rutas relativas.

Resumen del orden y por qué:

| Paso | Qué | Por qué en este orden |
|---|---|---|
| 0 | Subir los cambios desde WSL | La VM solo recibe lo que está en Git |
| 1 | VM + Docker | Base de todo |
| 2 | Usuarios, SSH, UFW | Antes de poner secretos en la VM |
| 3 | `.env` | Lo necesitan los certificados, GPG y Compose |
| 4 | GPG | `backup.sh` y la app necesitan las llaves públicas |
| 5 | Certificados + `preflight.sh` | **Antes** del primer `up`: si falta `ca.pem`, Docker crea una carpeta y MySQL no arranca |
| 6 | `compose up`, seed, verificación | Ya está todo listo |
| 7 | Cron, backup y restore | Necesita los contenedores arriba |
| 8 | Métricas (R4) | Necesita el cron funcionando |
| 9 | Pruebas y evidencias | Al final, con todo funcionando |
| 10 | Prueba desde Windows | Lo que verá el jurado |

---

## 0. Antes de empezar (en WSL)

Este chat agregó y corrigió archivos. Cópialos al repo y súbelos:

| Archivo | Cambio |
|---|---|
| `scripts/gen_env.sh` | **Nuevo.** Crea el `.env` de la VM con secretos nuevos, sin nano. Valida `\r`, caracteres raros, permisos y que solo se publique el 443 |
| `scripts/preflight.sh` | **Nuevo.** Revisión antes del primer `compose up` (certificados, dueños, `ca.pem` como carpeta, GPG, `.env`) |
| `scripts/metrics_report.py` | **Nuevo.** Tabla (Markdown, en inglés) y gráfica PNG desde el CSV de `monitor.sh` |
| `docker-compose.yaml` | Volumen `app_gnupg` en `/srv/.gnupg`: sin él, la llave pública de documentos se pierde cada vez que se recrea `sarais_app` |
| `scripts/linux/setup_users.sh` | Ya no hace `chown -R`/`chmod -R` sobre las llaves ni el `.env`. Antes, si lo repetías después de crear los certificados, dejaba `server-key.pem` en `644` y con dueño equivocado |
| `.gitattributes` | **Nuevo.** Fuerza finales de línea LF en `.sh`, `.yaml`, `.sql`, `.env*`… |
| `.gitignore` | Agrega `*.zip` |

En la raíz del repo había **dos .zip** (`sarais_repo.zip`, `sarais_repo_seguridad.zip`). Son copias viejas del código: no deben ir a Git.

```bash
WSL$ cd ~/proyecto_integrador
WSL$ git rm --cached --ignore-unmatch -q sarais_repo.zip sarais_repo_seguridad.zip
WSL$ rm -f sarais_repo.zip sarais_repo_seguridad.zip
WSL$ chmod +x scripts/gen_env.sh scripts/preflight.sh
WSL$ git add --renormalize .          # aplica .gitattributes a lo que ya está en Git
WSL$ git status                       # revisa la lista: no debe aparecer .env, .pem, .key ni .zip
WSL$ git add -A && git commit -m "Despliegue VM: gen_env, preflight, metrics_report, volumen app_gnupg" && git push
```

En desarrollo, el volumen nuevo se crea solo: `docker compose up -d` (sin `-v`).

**Compruébalo:**
```bash
WSL$ git ls-files | grep -E '(^|/)\.env$|\.zip$|\.pem$|\.key$'     # vacío
WSL$ git ls-files --eol scripts/*.sh | grep crlf                    # vacío
```

> **Historial con `.env`:** el `.env` viejo sigue en el historial. En la VM usaremos secretos **nuevos**, así que no afecta al despliegue. Pero `check_permissions.sh` mostrará `[FAIL] .env aparece en el historial` (R13). Si el repositorio es **público**, límpialo con `git filter-repo` antes de entregar.

### Qué debes poder explicar
- Por qué `.gitattributes` evita que un `\r` rompa scripts y el `.env`.
- Por qué borrar el `.env` del índice no basta (sigue en el historial) y qué hicimos (rotar secretos).

---

## 1. Crear la VM e instalar Docker Engine

### 1.1 Red solo-anfitrión (una vez, en VirtualBox)
1. **Archivo → Herramientas → Administrador de red → Host-only Networks**.
2. Si no hay ninguna: **Crear**. Debe tener `192.168.56.1/24`.
3. **Desactiva el servidor DHCP** (la VM tendrá IP fija).

### 1.2 Crear la máquina
| Recurso | Valor | Por qué |
|---|---|---|
| CPU | 2 | MySQL + Mongo + app + Nginx sin trabarse |
| RAM | 4096 MB | MySQL 8.4 (~400 MB) + Mongo 7 (~300 MB) + app; queda margen para el build |
| Disco | 25 GB, dinámico | Imágenes (~2 GB), volúmenes, backups y logs |
| Adaptador 1 | NAT | Internet para `apt`, Docker Hub y GitHub |
| Adaptador 2 | Solo-anfitrión (el de 1.1) | Para que Windows llegue a `192.168.56.10` |

1. **Nueva** → nombre `sarais-vm`, ISO de **Ubuntu Server 22.04 LTS**, marca "omitir instalación desatendida".
2. Instala Ubuntu: usuario inicial `sysadmin`, marca **Install OpenSSH server**, no importes llaves, no instales snaps.

### 1.3 IP fija
```bash
VM$ ip -br a                                   # la 2.ª tarjeta suele ser enp0s8
VM$ sudo nano /etc/netplan/60-hostonly.yaml
```
```yaml
network:
  version: 2
  ethernets:
    enp0s8:
      dhcp4: false
      addresses: [192.168.56.10/24]
```
> En nano: usa **espacios**, no tabulaciones. Guarda con Ctrl+O, Enter, Ctrl+X.

```bash
VM$ sudo chmod 600 /etc/netplan/60-hostonly.yaml
VM$ sudo netplan apply
```

### 1.4 Hora y zona horaria (¡importante para el MFA!)
TOTP compara la hora del servidor con la de tu celular. Si el reloj de la VM se atrasa más de ~30 s, **ningún código funciona**.
```bash
VM$ sudo timedatectl set-timezone America/Bogota
VM$ timedatectl          # "System clock synchronized: yes" y "NTP service: active"
```

### 1.5 ¿La CPU virtual tiene AVX? (MongoDB 7 lo exige)
MongoDB 5.0 o superior necesita la instrucción **AVX**. Con Hyper-V activo (lo usan WSL2 y Docker Desktop), VirtualBox a veces no la entrega.
```bash
VM$ grep -o -m1 -w avx /proc/cpuinfo      # debe imprimir: avx
```
Si no imprime nada, Mongo morirá con `Illegal instruction` (código 132). Primero actualiza VirtualBox a la última 7.x y vuelve a probar. Si sigue sin AVX, avísame antes de seguir: la otra salida es desactivar Hyper-V, y eso apaga WSL2 y Docker Desktop mientras esté desactivado.

### 1.6 Docker Engine + plugin Compose (repositorio oficial)
```bash
VM$ sudo apt-get update && sudo apt-get -y upgrade
VM$ sudo apt-get install -y ca-certificates curl git gnupg rsync
VM$ sudo install -m 0755 -d /etc/apt/keyrings
VM$ sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
VM$ sudo chmod a+r /etc/apt/keyrings/docker.asc
VM$ echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
VM$ sudo apt-get update
VM$ sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

**Compruébalo:**
```bash
VM$ ip -br a | grep 192.168.56.10              # la IP fija
VM$ sudo docker run --rm hello-world           # "Hello from Docker!"
VM$ docker compose version                     # Docker Compose version v2.x
VM$ systemctl is-enabled docker                # enabled (arranca con la VM)
PS> ping 192.168.56.10                         # responde
```

### Qué debes poder explicar
- Para qué sirve cada adaptador (NAT = salida a Internet; solo-anfitrión = Windows ↔ VM).
- Por qué Docker Engine del repositorio oficial y no Docker Desktop ni el paquete `docker.io` de Ubuntu (versión actual y plugin compose v2; Desktop es para escritorio).
- Por qué el reloj importa para TOTP (el código depende de la hora en ventanas de 30 s).
- Por qué la llave GPG del repositorio de Docker (`signed-by`): `apt` solo acepta paquetes firmados por Docker.

---

## 2. Usuarios, SSH con llaves y firewall

### 2.1 Llaves SSH (una por cliente)
```bash
WSL$ ssh-keygen -t ed25519 -C "tu_nombre-wsl"          # Enter y pon una frase de paso
WSL$ scp ~/.ssh/id_ed25519.pub sysadmin@192.168.56.10:/tmp/wsl.pub
```
> Si desde WSL no llegas a la VM (`scp` se queda esperando): `cp ~/.ssh/id_ed25519.pub /mnt/c/Users/<tu_usuario>/wsl.pub` y cópiala desde PowerShell: `PS> scp $env:USERPROFILE\wsl.pub sysadmin@192.168.56.10:/tmp/`

Para el paso 10 también necesitas una llave de Windows:
```powershell
PS> ssh-keygen -t ed25519 -C "tu_nombre-windows"
PS> scp $env:USERPROFILE\.ssh\id_ed25519.pub sysadmin@192.168.56.10:/tmp/win.pub
```

### 2.2 Clonar el repositorio
```bash
VM$ ssh sysadmin@192.168.56.10                 # todavía con contraseña
VM$ sudo git clone https://github.com/<ORG>/<REPO>.git /opt/sarais
VM$ sudo git config --system --add safe.directory /opt/sarais
```
- Repositorio privado: GitHub pide usuario y un **token** (no la contraseña). En 2.6 lo cambiamos por una deploy key.
- `safe.directory`: el repo será de `sarais_ops`. Sin esta línea, `git` se niega a trabajar cuando lo usa otro usuario (por ejemplo `sudo ./scripts/check_permissions.sh`).

### 2.3 Usuarios, grupos y permisos
```bash
VM$ mkdir -p /tmp/keys
VM$ cat /tmp/wsl.pub /tmp/win.pub > /tmp/keys/sarais_admin.pub   # admin: WSL y Windows
VM$ cp /tmp/wsl.pub /tmp/keys/sarais_ops.pub
VM$ cp /tmp/wsl.pub /tmp/keys/sarais_auditor.pub                  # para la prueba 21
VM$ cd /opt/sarais
VM$ sudo ./scripts/linux/setup_users.sh /tmp/keys
VM$ sudo passwd sarais_admin                                      # SOLO para sudo, no para SSH
VM$ rm -rf /tmp/keys /tmp/*.pub
```

**Compruébalo** (deja abierta la sesión de `sysadmin`):
```bash
VM$ id sarais_admin sarais_ops sarais_auditor
#  admin: sudo,docker,sarais | ops: docker,sarais,sarais-ops | auditor: sarais,sarais-audit (SIN docker)
VM$ ls -ld /opt/sarais /var/backups/sarais /var/log/sarais
#  drwxr-sr-x sarais_ops sarais | drwx------ sarais_ops | drwxr-s--- sarais_ops sarais-audit
WSL$ ssh sarais_admin@192.168.56.10 'whoami'      # sarais_admin
WSL$ ssh sarais_ops@192.168.56.10 'whoami'        # sarais_ops
```

### 2.4 Endurecer SSH y activar UFW
Desde una sesión **nueva** como `sarais_admin` (no cierres la de `sysadmin` hasta comprobar):
```bash
WSL$ ssh sarais_admin@192.168.56.10
VM(admin)$ cd /opt/sarais
VM(admin)$ sudo ./scripts/linux/harden_ssh.sh
VM(admin)$ sudo ./scripts/linux/setup_ufw.sh 192.168.56.0/24
```

**Compruébalo:**
```bash
WSL$ ssh sarais_admin@192.168.56.10 'echo ok'                      # ok (con llave)
WSL$ ssh -o PubkeyAuthentication=no sarais_admin@192.168.56.10     # Permission denied (publickey)
WSL$ ssh sysadmin@192.168.56.10                                    # Permission denied (no está en el grupo sarais)
VM(admin)$ sudo ufw status verbose     # deny (incoming) · 22/tcp LIMIT IN 192.168.56.0/24 · 443/tcp ALLOW IN
```
Si te bloqueas: entra por la **consola de VirtualBox** como `sysadmin` y borra `/etc/ssh/sshd_config.d/01-sarais-hardening.conf`.

### 2.5 Recordatorio: UFW y Docker
Docker escribe sus propias reglas de iptables. Un puerto **publicado** por un contenedor **no pasa por UFW**. Por eso la protección real de las bases de datos es que **no se publican** (paso 3: `COMPOSE_FILE` ignora el override).

### 2.6 Deploy key (git pull sin contraseña, solo lectura)
```bash
VM(admin)$ sudo -iu sarais_ops
VM(ops)$ ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N "" -C "sarais-vm"
VM(ops)$ cat ~/.ssh/github_deploy.pub
```
GitHub → repositorio → **Settings → Deploy keys → Add deploy key**. Pega la llave. **No** marques "Allow write access".
```bash
VM(ops)$ printf 'Host github.com\n  IdentityFile ~/.ssh/github_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config
VM(ops)$ chmod 600 ~/.ssh/config
VM(ops)$ cd /opt/sarais && git remote set-url origin git@github.com:<ORG>/<REPO>.git
VM(ops)$ git pull                     # la 1.ª vez escribe "yes" para la huella de github.com
```
**Compruébalo:** `git pull` dice `Already up to date.` sin pedir contraseña.

### Qué debes poder explicar
- Mínimo privilegio: qué puede hacer cada usuario y por qué el auditor **no** está en `docker` (grupo `docker` = root, riesgo R11).
- Por qué solo llaves (no hay contraseña que adivinar) y por qué `harden_ssh.sh` valida con `sshd -t` antes de recargar.
- Qué hace `ufw limit` (bloquea 6+ conexiones en 30 s) y por qué SSH solo desde `192.168.56.0/24`.
- Por qué la deploy key es de solo lectura: si roban la VM, no pueden modificar el repositorio.

---

## 3. El `.env` de la VM (sin nano)

Ya nos falló editar el `.env` a mano (finales de Windows y caracteres extra). Por eso **no lo edites**: lo genera `gen_env.sh`.

```bash
VM(ops)$ cd /opt/sarais
VM(ops)$ ./scripts/gen_env.sh
```
Qué hace:
1. Parte de `.env.example` (quitando cualquier `\r`).
2. Activa `COMPOSE_FILE=docker-compose.yaml` (la VM ignora el override: bases de datos sin puertos).
3. Genera **secretos nuevos**: contraseñas `openssl rand -hex 24`, `APP_SECRET_KEY` de 64 caracteres, `APP_TOTP_ENC_KEY` de 32 bytes en base64.
4. Deja el archivo en `600` y lo valida.
5. Se niega a sobrescribir un `.env` existente (las bases ya creadas usan esas contraseñas).

Para cambiar un valor después, tampoco uses nano:
```bash
VM(ops)$ ./scripts/gen_env.sh --set CLAVE=VALOR
```

**Compruébalo:**
```bash
VM(ops)$ ./scripts/gen_env.sh --check
#  [OK] puertos publicados: solo 443
#  [INFO] .env válido (permisos 600, sin \r, sin valores por defecto)
VM(ops)$ ls -l .env                                   # -rw------- sarais_ops
VM(ops)$ cat -A .env | grep -c '\^M'                  # 0  (^M sería un \r)
VM(ops)$ git status --short                           # .env NO aparece (está ignorado)
```
No muestres el `.env` en pantalla durante la sustentación.

> Guarda una copia del `.env` de la VM **fuera** de la VM (gestor de contraseñas). Sin él, no podrás volver a levantar las bases con los volúmenes actuales.

### Qué debes poder explicar
- Por qué secretos distintos a desarrollo (el `.env` de desarrollo está en el historial de Git: R13).
- Por qué contraseñas solo alfanuméricas (van dentro de SQL y de la URI de Mongo).
- Qué pasa si cambias `APP_TOTP_ENC_KEY` (nadie puede descifrar su secreto MFA: todos deben registrar el QR de nuevo).
- Por qué `COMPOSE_FILE` protege las bases de datos.

---

## 4. Llaves GPG (privadas en WSL, públicas en la VM)

Dos llaves, cada una con un solo uso:

| Llave | La usa | Pública en | Privada en |
|---|---|---|---|
| `sarais-vm-backup@example.local` | `backup.sh` (host) | llavero de `sarais_ops` | tu PC (WSL) + copia offline |
| `sarais-vm-docs@example.local` | la app (`encrypt_document`) | dentro de `sarais_app` (volumen `app_gnupg`) | tu PC (WSL) + copia offline |

### 4.1 Generar en WSL
```bash
WSL$ export GPG_TTY=$(tty)
WSL$ gpg --quick-gen-key "SARAIS VM Backup <sarais-vm-backup@example.local>" rsa3072 encrypt 2y
WSL$ gpg --quick-gen-key "SARAIS VM Docs <sarais-vm-docs@example.local>"     rsa3072 encrypt 2y
```
Pon una **frase de paso** a cada una: protege la llave privada si alguien copia tu llavero.

Huellas (40 caracteres):
```bash
WSL$ BK=$(gpg --list-keys --with-colons sarais-vm-backup@example.local | awk -F: '/^fpr/{print $10; exit}')
WSL$ DK=$(gpg --list-keys --with-colons sarais-vm-docs@example.local   | awk -F: '/^fpr/{print $10; exit}')
WSL$ echo "BACKUP=$BK"; echo "DOCS=$DK"          # anótalas
```

### 4.2 Exportar
```bash
WSL$ mkdir -p ~/sarais_keys && chmod 700 ~/sarais_keys      # FUERA del repo
WSL$ gpg --armor --export "$BK" > ~/sarais_keys/backup_pub.asc
WSL$ gpg --armor --export "$DK" > ~/sarais_keys/docs_pub.asc
WSL$ gpg --armor --export-secret-keys "$BK" "$DK" > ~/sarais_keys/PRIVATE_vm_keys.asc   # pide la frase
WSL$ chmod 600 ~/sarais_keys/*
```
Copia `PRIVATE_vm_keys.asc` a una USB (riesgo R10: sin la privada, los backups no sirven). **Nunca** la copies a la VM ni al repo.

### 4.3 Importar las públicas en la VM
```bash
WSL$ scp ~/sarais_keys/backup_pub.asc ~/sarais_keys/docs_pub.asc sarais_ops@192.168.56.10:/tmp/
VM(ops)$ install -d -m 700 ~/keys && mv /tmp/backup_pub.asc /tmp/docs_pub.asc ~/keys/
VM(ops)$ gpg --import ~/keys/backup_pub.asc
VM(ops)$ cd /opt/sarais
VM(ops)$ ./scripts/gen_env.sh --set BACKUP_GPG_RECIPIENT=<HUELLA_BACKUP> --set DOCS_GPG_RECIPIENT=<HUELLA_DOCS>
```
`docs_pub.asc` se importa en `sarais_app` en el paso 6 (el contenedor aún no existe).

**Compruébalo:**
```bash
VM(ops)$ gpg --list-keys                    # aparece sarais-vm-backup
VM(ops)$ gpg --list-secret-keys             # VACÍO: en la VM no hay llaves privadas
VM(ops)$ ./scripts/gen_env.sh --check       # sigue válido
```

### Qué debes poder explicar
- Cifrado asimétrico: con la pública se cifra, solo la privada descifra. Si roban la VM, los backups y documentos siguen ilegibles.
- Por qué la **huella** y no el correo en `*_GPG_RECIPIENT` (otra llave con el mismo correo podría elegirse por error).
- Por qué dos llaves (si se compromete una, la otra sigue segura; separación de usos).
- Riesgo R10: perder la privada = perder los backups. Por eso hay copia offline.

---

## 5. Certificados TLS y revisión previa (ANTES del primer `up`)

Como `sarais_admin` (necesita sudo):
```bash
VM(admin)$ cd /opt/sarais
VM(admin)$ sudo ./scripts/gen_certs.sh 192.168.56.10      # Nginx: CN y SAN con la IP
VM(admin)$ sudo ./scripts/gen_mysql_certs.sh              # CA interna + certificado de mysql_db
VM(admin)$ sudo ./scripts/preflight.sh
```
`preflight.sh` revisa todo lo que ya nos falló: `ca.pem` como carpeta, dueños y permisos de cada llave, que el certificado incluya `192.168.56.10`, el `.env`, la llave GPG de backups (y que **no** haya privadas), las carpetas de backups y logs, y Docker.

**Compruébalo:** `Resultado: N PASS, 0 FAIL` y `Listo para: docker compose up -d --build`.

Para mirar las llaves tú mismo (como `sarais_ops` no las ves: es lo correcto):
```bash
VM(admin)$ sudo ls -l docker/nginx/certs docker/mysql/certs docker/mysql/ca-private
#  sarais.key 640 root:101 · server-key.pem 600 999:999 · ca-key.pem 600 root:root
```

### Qué debes poder explicar
- Por qué Docker crea una **carpeta** `ca.pem` si el archivo no existe (un bind mount de una ruta inexistente se crea como directorio) y por qué entonces MySQL no arranca.
- Por qué la llave de Nginx es del grupo 101 y la de MySQL del UID 999 (son los usuarios no root dentro de cada contenedor).
- Por qué `ca-key.pem` no se monta en ningún contenedor (con ella se pueden firmar certificados falsos).
- Por qué el certificado de Nginx es autofirmado y qué riesgo deja (R6: el navegador avisa; en producción, una CA reconocida).

---

## 6. Levantar, cargar datos y verificar

### 6.1 Primer arranque
```bash
VM(ops)$ cd /opt/sarais
VM(ops)$ docker compose up -d --build
VM(ops)$ watch -n 5 docker compose ps        # Ctrl+C cuando los 4 digan (healthy). MySQL tarda 1-2 min la 1.ª vez
```

### 6.2 Keyring de MySQL en 600
Cada volumen nuevo crea el keyring en `640`.
```bash
VM(ops)$ docker exec mysql_db chmod 600 /var/lib/mysql-keyring/component_keyring_file
VM(ops)$ docker exec mysql_db stat -c '%a %U' /var/lib/mysql-keyring/component_keyring_file   # 600 mysql
```

### 6.3 Llave pública de documentos en la app
```bash
VM(ops)$ docker exec -i sarais_app gpg --batch --import < ~/keys/docs_pub.asc
VM(ops)$ docker exec sarais_app gpg --list-keys            # aparece sarais-vm-docs
VM(ops)$ docker exec sarais_app gpg --list-secret-keys     # VACÍO (prueba 3.6)
VM(ops)$ docker compose up -d --force-recreate app         # recrea el contenedor...
VM(ops)$ docker exec sarais_app gpg --list-keys            # ...y la llave sigue ahí (volumen app_gnupg)
```

### 6.4 Datos demo (hashes Argon2 reales)
En la VM no hay `APP_ENV=development`, así que la app se considera producción y `seed_data` pide `--allow-production` a propósito. La contraseña demo se lee sin mostrarla y no queda en el historial:
```bash
VM(ops)$ read -rs -p "Contraseña demo (12+ caracteres, distinta a desarrollo): " SEED_PASSWORD; echo
VM(ops)$ export SEED_PASSWORD
VM(ops)$ docker exec -e SEED_PASSWORD sarais_app python -m app.scripts.seed_data --allow-production
VM(ops)$ unset SEED_PASSWORD
```
Esperado: `[seed] Hashes reemplazados: N`.

### 6.5 Verificación
```bash
VM(ops)$ ./scripts/verify_encryption.sh            # 0 FAIL (keyring 600 → PASS, no WARN)
VM(admin)$ sudo ./scripts/check_permissions.sh     # solo 1 problema esperado: ".env aparece en el historial" (R13)
VM(admin)$ sudo ss -tlnp | grep -E ':(22|443|3306|27017|8000)\b'   # solo :22 y :443
```

### Qué debes poder explicar
- Qué hace `--build` y por qué los datos no se pierden con `up` (viven en volúmenes).
- Por qué **nunca** `down -v` en la VM (borra `mysql_keyring` → datos cifrados irrecuperables).
- Por qué el keyring debe estar en `600` (solo el usuario `mysql` lee la llave maestra).
- Por qué la contraseña demo va por variable de entorno y `read -s` (no queda en el código, ni en la pantalla, ni en `.bash_history`).

---

## 7. Cron, backup y restore

### 7.1 Instalar el cron
```bash
VM(ops)$ crontab /opt/sarais/scripts/crontab.example
VM(ops)$ crontab -l
```
| Tarea | Cuándo |
|---|---|
| `backup.sh` | todos los días 2:00 a. m. |
| `monitor.sh` | cada 5 minutos |
| `cleanup.sh` | domingos 3:30 a. m. |

### 7.2 Probar un backup
1. En la app de la VM, como **docente**, cambia una nota de un estudiante sintético a un valor fácil de reconocer (por ejemplo `4.37`). Anota estudiante, asignatura y periodo.
2. Haz el backup:
```bash
VM(ops)$ ./scripts/backup.sh                                   # termina en "Backup terminado correctamente"
VM(ops)$ ls -l /var/backups/sarais/                            # .gpg y .sha256, permisos -rw-------
VM(ops)$ file /var/backups/sarais/*.gpg                        # PGP RSA encrypted session key
VM(ops)$ zgrep -c CREATE /var/backups/sarais/*.gpg             # 0: no hay texto legible
VM(ops)$ ./scripts/cleanup.sh --dry-run                        # [dry-run], no borra nada
```

### 7.3 Probar el restore (en WSL: ahí está la llave privada)
```bash
WSL$ mkdir -p ~/sarais_backups
WSL$ scp 'sarais_ops@192.168.56.10:/var/backups/sarais/sarais_*' ~/sarais_backups/
WSL$ export GPG_TTY=$(tty)
WSL$ F=$(ls -t ~/sarais_backups/sarais_*.tar.gz.gpg | head -1); echo "$F"
WSL$ gpg -d "$F" | tar -tzf -          # pide la frase; lista MANIFEST.txt, mysql_dump.sql, mongo_dump..., documents.tar
```
Ese `gpg -d` deja la frase en memoria del agente: así `restore.sh` (que usa `--batch`) no falla.

Entorno limpio (en **desarrollo** sí se permite `down -v`):
```bash
WSL$ cd ~/proyecto_integrador
WSL$ docker compose down -v && docker compose up -d
WSL$ docker compose ps                                   # espera "healthy"
WSL$ ./scripts/restore.sh --yes "$F"
```
Esperado: `Checksum SHA-256 correcto` → manifiesto → `MySQL restaurado: N tablas/vistas` → `MongoDB restaurado: audit_logs tiene N documentos` → `Restauración terminada`.

**Compruébalo con SQL** (Workbench o terminal):
```sql
SELECT grade_id, score, updated_at FROM grades ORDER BY updated_at DESC LIMIT 3;
```
Debe aparecer la nota `4.37` del paso 1.

> No intentes entrar a la app de WSL con los usuarios restaurados: sus secretos MFA están cifrados con la `APP_TOTP_ENC_KEY` **de la VM**, que no existe en desarrollo. La app te devolverá a `/login` (sin error 500). Eso es **correcto**: demuestra que el backup solo no basta para suplantar el MFA. Para volver a usar tu entorno de desarrollo normal: `docker compose down -v && docker compose up -d` y el `seed_data` de siempre.

**Checksum alterado (prueba 12):**
```bash
WSL$ cp "$F" /tmp/x.tar.gz.gpg && cp "$F.sha256" /tmp/x.tar.gz.gpg.sha256
WSL$ sed -i "s/$(basename "$F")/x.tar.gz.gpg/" /tmp/x.tar.gz.gpg.sha256
WSL$ printf 'X' >> /tmp/x.tar.gz.gpg
WSL$ ./scripts/restore.sh --yes /tmp/x.tar.gz.gpg      # "El checksum NO coincide" y termina con error
```

### Qué debes poder explicar
- Qué contiene el backup (dump lógico de MySQL, `mongodump`, documentos ya cifrados, manifiesto con SHA-256) y por qué no depende del keyring.
- Por qué nunca se escribe el `.tar` sin cifrar en disco (tubería `tar | gpg`).
- Para qué sirve el `.sha256` (integridad) frente a GPG (confidencialidad).
- Por qué el restore se prueba en otro entorno (la privada no está en la VM; un backup no probado no es un backup).

---

## 8. Métricas de recursos (R4)

### 8.1 Recolección continua
`monitor.sh` ya corre cada 5 minutos por cron (paso 7). Cada fila: CPU, carga, RAM, swap, disco, procesos, estado de los 4 contenedores y `OK` o `ALERT:...`.
```bash
VM(ops)$ ls -l /var/log/sarais/metrics/
VM(ops)$ tail -n 3 /var/log/sarais/metrics/metrics_$(date +%Y-%m).csv
```
Deja la VM encendida **al menos 24 h** (288 mediciones) antes de sacar la tabla. Durante ese tiempo usa la app un rato (logins, notas, asistencia) para que haya actividad real.

### 8.2 Tabla y gráfica para el informe (en WSL)
```bash
WSL$ cd ~/proyecto_integrador && source .venv/bin/activate
WSL$ pip install matplotlib                      # solo la primera vez
WSL$ mkdir -p ~/sarais_metrics docs/img
WSL$ scp 'sarais_ops@192.168.56.10:/var/log/sarais/metrics/metrics_*.csv' ~/sarais_metrics/
WSL$ python3 scripts/metrics_report.py ~/sarais_metrics/metrics_*.csv --png docs/img/vm_metrics.png
```
- La **tabla** sale en Markdown y en inglés (min, promedio, p95, máximo de CPU, RAM, disco, carga, procesos; % de mediciones con los 4 contenedores sanos; alertas). Pégala en el informe IEEE.
- La **gráfica** tiene 3 paneles (CPU, RAM, disco) con la misma escala 0–100 % y la línea del umbral de alerta (85 %).
- Para un intervalo concreto: `--since 2026-11-18T08:00 --until 2026-11-19T08:00`.

### 8.3 Medición en vivo (sustentación)
Sesión SSH 1, línea base:
```bash
VM(ops)$ cd /opt/sarais
VM(ops)$ ./scripts/monitor.sh | cut -d, -f1,3,7,9,15-19     # hora, CPU, RAM, disco, contenedores, estado
VM(ops)$ docker stats --no-stream                          # CPU y RAM por contenedor
```
Sesión SSH 2, carga artificial de 60 s en las 2 CPU:
```bash
VM(ops)$ timeout 60 yes > /dev/null & timeout 60 yes > /dev/null &
```
De vuelta en la sesión 1, mientras dura la carga:
```bash
VM(ops)$ for i in 1 2 3 4; do ./scripts/monitor.sh | cut -d, -f1,3,19; sleep 10; done
#  la CPU sube a ~100 % y el estado pasa a ALERT:CPU; al terminar vuelve a OK
VM(ops)$ python3 scripts/metrics_report.py /var/log/sarais/metrics/metrics_$(date +%Y-%m).csv --since "$(date +%Y-%m-%dT%H:00)"
#  tabla en vivo (en la VM no hay matplotlib: solo tabla, es lo esperado)
```
Alerta por servicio caído (prueba 14):
```bash
VM(ops)$ docker stop mongo_db; ./scripts/monitor.sh | cut -d, -f18,19; docker start mongo_db
#  stopped,ALERT:mongo
```

### Qué debes poder explicar
- De dónde sale cada métrica (`/proc/stat` con dos lecturas a 1 s, `/proc/meminfo` con `MemAvailable`, `df`, `ps`, `docker inspect` del healthcheck).
- Por qué un CSV por mes y por qué `cleanup.sh` lo comprime a los 35 días y lo borra a los 90.
- Qué es el p95 (el 95 % de las mediciones está por debajo: ignora picos aislados).
- Por qué 2 CPU / 4 GB alcanzan para este caso, con los números de tu tabla.

---

## 9. Pruebas en la VM y evidencias

### 9.1 Las 21 pruebas de infraestructura
Están en `docs/infrastructure_guide.md` §5. Ya hiciste varias en los pasos anteriores; córrelas todas de nuevo en orden para las capturas. Ajustes para la VM:

| # | Nota |
|---|---|
| 3 | `sudo ss -tlnp` como `sarais_admin` |
| 5 | `openssl s_client -connect 127.0.0.1:443` dentro de la VM |
| 6–8 | `docker exec -it mysql_db ...` como `sarais_ops` |
| 11–12 | Se hacen en WSL (paso 7.3) |
| 16 | Espera 5 min después de instalar el cron |
| 17–18 | Desde WSL o PowerShell |
| 21 | `WSL$ ssh sarais_auditor@192.168.56.10` y corre los tres comandos |

### 9.2 Pruebas de seguridad (`docs/security_tests.md`)
Cambia `localhost` por `127.0.0.1` cuando corras dentro de la VM, o por `192.168.56.10` desde Windows/WSL.

| Sección | Dónde | Nota |
|---|---|---|
| 0.1 pytest | **WSL** | En la VM no hay entorno de desarrollo; es evidencia del código (87 PASS) |
| 0.2, 0.5 | VM | `verify_encryption.sh` (ops) y `sudo check_permissions.sh` (admin; 1 problema esperado: historial) |
| 0.3, 0.4 | VM | Comandos en la cabecera de cada `.js` y en `db/mongo/README.md` |
| 1.x TLS | VM | 1.5 dentro de la VM: `curl -m 3 http://127.0.0.1` → `Connection refused`. Desde Windows el 80 da **tiempo agotado** (UFW descarta): también es válido |
| 2.x MySQL | VM | 2.8 (Workbench) **no aplica**: en la VM el 3306 no se publica. Esa es la prueba 4 de infraestructura |
| 3.x reposo | VM | 3.5 cuando exista la subida de documentos |
| 4–6 roles, MFA, bloqueo | Navegador en Windows | `https://192.168.56.10` |
| 6.4 limit_req | VM | `for i in $(seq 12); do curl -sk -o /dev/null -w "%{http_code}\n" -d "username=x&password=y" https://127.0.0.1/login; done` → aparecen `503` |
| 7.2 IP real | Navegador | En `/admin/audit` la IP debe ser `192.168.56.1` (Windows), no `172.x` |
| 8.x secretos | VM | 8.2 **dará resultado** (historial): documenta que los secretos se rotaron (R13) |

### 9.3 Capturas que debes guardar
Nombra cada archivo con el número de prueba, por ejemplo `INF-07_tablas_cifradas.png`, `SEC-5.5_totp_reutilizado.png`. Guárdalas en `docs/evidence/` (solo capturas, sin secretos visibles).

| # | Captura | Qué debe verse |
|---|---|---|
| E1 | VirtualBox: configuración de la VM | 2 CPU, 4 GB, NAT + solo-anfitrión |
| E2 | `ip -br a` y `timedatectl` | `192.168.56.10/24`, reloj sincronizado |
| E3 | `docker compose version` + `hello-world` | Docker Engine instalado |
| E4 | `id` de los 3 usuarios + `ls -ld` de carpetas | Grupos y permisos (mínimo privilegio) |
| E5 | `sshd -T` filtrado + intento sin llave + intento root | `passwordauthentication no`, `Permission denied` |
| E6 | `ufw status verbose` | deny incoming, 22 LIMIT, 443 ALLOW |
| E7 | `gen_env.sh --check` + `ls -l .env` | `.env` válido, `600`, solo 443 |
| E8 | `gpg --list-keys` y `--list-secret-keys` (ops y app) | Públicas sí, privadas vacío |
| E9 | `preflight.sh` | `0 FAIL` |
| E10 | `docker compose ps` | 4 `healthy` |
| E11 | `docker exec ... id` de los 4 contenedores | UID 10001 · 999 · 999 · 101 |
| E12 | `ss -tlnp` + `Test-NetConnection -Port 3306` | Solo 22 y 443; 3306 `False` |
| E13 | `verify_encryption.sh` | `16 PASS, 0 FAIL` |
| E14 | Tablas `ENCRYPTION = Y` + `grep -c` en `.ibd` = 0 | Cifrado en reposo |
| E15 | Error 3159 sin TLS + `Ssl_version TLSv1.3` + `sarais_app → SSL/TLS` | Cifrado en tránsito |
| E16 | Error 1142 (DELETE y DROP) | Mínimo privilegio en MySQL |
| E17 | `openssl s_client` TLS 1.1 falla / 1.2 y 1.3 OK | Protocolos de Nginx |
| E18 | `curl -skI` con cabeceras | HSTS, CSP (una sola), `server: nginx` sin versión |
| E19 | Navegador: candado/aviso y detalles del certificado | `CN = 192.168.56.10` |
| E20 | Pantalla del QR + F12 Red | Peticiones solo a `192.168.56.10` |
| E21 | Login con MFA correcto, código errado, código reutilizado | `mfa_failed` en la auditoría |
| E22 | 403 de student y teacher en rutas ajenas | RBAC |
| E23 | Bloqueo tras 5 intentos + mensaje genérico | `account_locked` |
| E24 | `503` de Nginx por `limit_req` | Límite de peticiones |
| E25 | `/admin/audit` | Eventos con IP real y sin datos personales |
| E26 | `deleteOne` en Mongo con `sarais_app` | Error 13 (auditoría solo-agregar) |
| E27 | `backup.sh` + `file` + `zgrep -c` | Backup cifrado |
| E28 | `restore.sh` en WSL + `SELECT` con la nota marcada | Restauración probada |
| E29 | Checksum alterado | `El checksum NO coincide` |
| E30 | `crontab -l` + `tail` del CSV | Automatización |
| E31 | Tabla de `metrics_report.py` + `vm_metrics.png` | Requisito R4 |
| E32 | `ALERT:CPU` y `ALERT:mongo` | Alertas del monitoreo |
| E33 | Auditor: lee el log, `docker ps` y `.env` denegados | Separación de funciones |
| E34 | `docker inspect ... grep -c KEY` | Evidencia del riesgo R11/R14 (aceptado) |

### Qué debes poder explicar
- Cada prueba: qué control demuestra y qué riesgo de la matriz mitiga.
- Por qué algunas pruebas dan "error" a propósito (3159, 1142, 403, 503, 13): el error **es** el resultado esperado.

---

## 10. Prueba final desde Windows

### 10.1 Navegador
1. Abre `https://192.168.56.10`. Aparece "La conexión no es privada" (certificado autofirmado). **Configuración avanzada → Continuar**.
2. Revisa el certificado (clic en el aviso del candado): emitido para `192.168.56.10`.
3. Entra como `admin.demo` (o el usuario de `dml.sql`) con la contraseña demo del paso 6.4.
4. Primera vez: aparece el **QR**. Escanéalo con Google Authenticator, Microsoft Authenticator o Aegis, escribe el código. Entra.
5. Cierra sesión y entra de nuevo con un código **nuevo**.
6. Repite con un docente y un estudiante.

**Compruébalo:** en `/admin/audit` aparecen `mfa_enabled` y `login_success` con IP `192.168.56.1`.

### 10.2 SSH con llave desde Windows
```powershell
PS> ssh sarais_admin@192.168.56.10                                   # entra con tu llave de Windows (pide su frase)
PS> ssh -o PubkeyAuthentication=no sarais_admin@192.168.56.10        # Permission denied (publickey)
PS> ssh root@192.168.56.10                                           # Permission denied (publickey)
PS> Test-NetConnection 192.168.56.10 -Port 443                       # TcpTestSucceeded : True
PS> Test-NetConnection 192.168.56.10 -Port 3306                      # TcpTestSucceeded : False
PS> Test-NetConnection 192.168.56.10 -Port 27017                     # TcpTestSucceeded : False
```

### Qué debes poder explicar
- El camino de una petición: navegador → TLS → Nginx (443 en la VM → 8443 en el contenedor) → app (red `frontend`) → MySQL con TLS y Mongo (red `backend`, interna).
- Por qué el navegador avisa y por qué igual la conexión está cifrada.
- Los dos factores del login: algo que sabes (contraseña, Argon2) y algo que tienes (celular con el secreto TOTP).

---

## 11. Problemas comunes en la VM

| Síntoma | Causa y solución |
|---|---|
| `mysql_db` reinicia: `Is a directory` o error con `ca.pem` | Hiciste `up` sin certificados: `docker compose down` (sin `-v`) → `sudo rmdir docker/mysql/certs/ca.pem` → `sudo ./scripts/gen_mysql_certs.sh` → `sudo ./scripts/preflight.sh` → `up -d` |
| `mongo_db` sale con código 132 / `Illegal instruction` | La CPU virtual no tiene AVX (paso 1.5) |
| `gen_env.sh`: "Ya existe .env" | Correcto: no se sobrescribe. Usa `--check` o `--set`. Solo si las bases están vacías: `FORCE=1 ./scripts/gen_env.sh` |
| Login con usuario demo falla siempre | No corriste `seed_data` (paso 6.4): los hashes siguen como `ARGON2_HASH_PLACEHOLDER` |
| Ningún código MFA sirve | Reloj de la VM desfasado: `timedatectl`. Revisa también la hora del celular (automática) |
| `backup.sh`: no está la llave pública | La importaste con otro usuario. El llavero GPG es por usuario: impórtala como `sarais_ops` |
| `restore.sh`: "No se pudo descifrar" | `export GPG_TTY=$(tty)` y desbloquea antes con `gpg -d "$F" \| tar -tzf -` |
| `check_permissions.sh` no ve las llaves | Corre con `sudo` (las carpetas de llaves solo las ve root) |
| `git`: `dubious ownership` | `sudo git config --system --add safe.directory /opt/sarais` |
| `scp`/`ssh` desde WSL se quedan esperando | Usa PowerShell y pasa los archivos por `/mnt/c/Users/<tu_usuario>/` |
| `verify_encryption.sh`: `WARN permisos keyring 640` | Paso 6.2 |
| Después de `git pull`, falla un script con `\r` | `git ls-files --eol \| grep crlf`. Con `.gitattributes` no debería pasar |
| Te bloqueaste por SSH | Consola de VirtualBox como `sysadmin` → borra `/etc/ssh/sshd_config.d/01-sarais-hardening.conf` → `sudo systemctl reload ssh` |

**Reglas de oro en la VM:** nunca `docker compose down -v`; nunca la llave privada GPG en la VM; nunca editar `.env` con nano o desde Windows; siempre desde `/opt/sarais`.
