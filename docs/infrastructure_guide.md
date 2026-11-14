# SARAIS: guía de infraestructura (paso a paso)

Esta guía es para personas que no son desarrolladoras. Copia los comandos tal cual.
- `PC$` = terminal de Ubuntu (WSL2) en tu computador.
- `PS>` = PowerShell de Windows.
- `VM$` = terminal de la máquina virtual (por SSH).

---

## 0. Qué contiene el repositorio

```
docker-compose.yaml              # base: lo que corre en la VM (solo publica 443)
docker-compose.override.yaml     # solo desarrollo: puertos en 127.0.0.1
.env.example                     # plantilla de secretos (.env NO va a Git)
docker/
  nginx/  Dockerfile, nginx.conf, proxy_params_sarais, .dockerignore, certs/
  app/    Dockerfile                    (su .dockerignore está en app/)
  mysql/  Dockerfile, conf.d/sarais.cnf, keyring/, init/05_users.sh, .dockerignore
  mongo/  Dockerfile, .dockerignore
scripts/
  lib/common.sh                  # funciones compartidas (logs, .env, bloqueo)
  backup.sh  restore.sh  monitor.sh  cleanup.sh  gen_certs.sh
  crontab.example
  linux/ setup_users.sh  harden_ssh.sh  setup_ufw.sh
```

### Servicios y redes

| Servicio | Contenedor | Usuario dentro | Redes | Puerto en la VM |
|---|---|---|---|---|
| nginx | sarais_nginx | nginx (101) | frontend | 443 |
| app | sarais_app | sarais (10001) | frontend + backend | ninguno |
| mysql_db | mysql_db | mysql (999) | backend | ninguno |
| mongo_db | mongo_db | mongodb (999) | backend | ninguno |

- `backend` es **interna**: no tiene salida a Internet y no se puede alcanzar desde fuera.
- Nginx no puede hablar con las bases de datos porque no está en `backend`.

---

## 1. Primer arranque en desarrollo (WSL2)

```bash
PC$ cd ~/sarais
PC$ cp .env.example .env
PC$ nano .env                      # cambia cada "cambia_esto"
PC$ openssl rand -hex 24           # úsalo para generar cada contraseña
PC$ sudo ./scripts/gen_certs.sh localhost
PC$ docker compose up -d --build
PC$ docker compose ps              # espera a que los 4 servicios digan "healthy"
```

Compruébalo en Windows: abre `https://localhost`. El navegador avisará "no es seguro" porque el certificado es autofirmado. Eso es lo esperado: acepta el aviso.

> La app debe tener la ruta `GET /health` que responda 200. Sin ella, `sarais_app` se queda en "unhealthy" y Nginx no arranca.

---

## 2. Crear la VM en VirtualBox

### 2.1 Red del anfitrión (una sola vez)
1. VirtualBox → **Archivo → Herramientas → Administrador de red** (Network Manager).
2. Pestaña **Host-only Networks**. Si no hay ninguna, presiona **Crear**.
3. Revisa que tenga la IP `192.168.56.1/24`. **Desactiva el servidor DHCP**: pondremos una IP fija.

### 2.2 La máquina
1. Descarga **Ubuntu Server 22.04 LTS** (ISO) de ubuntu.com.
2. **Nueva** → nombre `sarais-vm`, ISO descargada. Marca "omitir instalación desatendida".
3. Recursos: **2 CPU, 4096 MB RAM, disco de 25 GB**.
4. **Configuración → Red**:
   - Adaptador 1: **NAT** (le da Internet a la VM).
   - Adaptador 2: **Adaptador solo-anfitrión** (Host-only), el de 2.1 (para que Windows la vea).
5. Inicia la VM e instala Ubuntu:
   - Usuario inicial: `sysadmin` (solo se usa para la instalación).
   - Marca **Install OpenSSH server**. **No** importes llaves.
   - No marques ningún "snap" adicional (Docker lo instalamos después).

### 2.3 IP fija en la red solo-anfitrión
En la consola de la VM:
```bash
VM$ ip -br a                       # busca la 2.ª tarjeta, normalmente enp0s8
VM$ sudo nano /etc/netplan/60-hostonly.yaml
```
Contenido (cambia `enp0s8` si tu tarjeta tiene otro nombre):
```yaml
network:
  version: 2
  ethernets:
    enp0s8:
      dhcp4: false
      addresses: [192.168.56.10/24]
```
```bash
VM$ sudo chmod 600 /etc/netplan/60-hostonly.yaml
VM$ sudo netplan apply
VM$ ip -br a                       # enp0s8 debe mostrar 192.168.56.10/24
```
Desde Windows:
```powershell
PS> ping 192.168.56.10
PS> ssh sysadmin@192.168.56.10     # todavía con contraseña; luego se desactiva
```

---

## 3. Preparar la VM

### 3.1 Actualizar e instalar Docker (repositorio oficial de Docker)
```bash
VM$ sudo apt-get update && sudo apt-get -y upgrade
VM$ sudo apt-get install -y ca-certificates curl git gnupg rsync
VM$ sudo install -m 0755 -d /etc/apt/keyrings
VM$ sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
VM$ sudo chmod a+r /etc/apt/keyrings/docker.asc
VM$ echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
VM$ sudo apt-get update
VM$ sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
VM$ sudo docker run --rm hello-world   # debe decir "Hello from Docker!"
```

### 3.2 Tu llave SSH (en Windows)
```powershell
PS> ssh-keygen -t ed25519 -C "tu_nombre"      # Enter a todo; pon una frase de paso
PS> scp $env:USERPROFILE\.ssh\id_ed25519.pub sysadmin@192.168.56.10:/tmp/
```
En la VM, prepara la carpeta de llaves (una llave por usuario):
```bash
VM$ mkdir -p /tmp/keys
VM$ cp /tmp/id_ed25519.pub /tmp/keys/sarais_admin.pub
VM$ cp /tmp/id_ed25519.pub /tmp/keys/sarais_ops.pub
```
(En el equipo, cada integrante puede tener su propia llave. Para la demo basta una.)

### 3.3 Clonar el repositorio
```bash
VM$ sudo git clone https://github.com/<ORG>/<REPO>.git /opt/sarais
```
Si el repositorio es privado, GitHub pide usuario y un **token** (no tu contraseña). Luego lo cambiamos por una deploy key (3.6).

### 3.4 Usuarios, grupos y permisos
```bash
VM$ cd /opt/sarais
VM$ sudo ./scripts/linux/setup_users.sh /tmp/keys
VM$ sudo passwd sarais_admin       # contraseña SOLO para usar sudo (no para SSH)
```
Prueba desde Windows **antes** de seguir (deja abierta la sesión de `sysadmin`):
```powershell
PS> ssh sarais_admin@192.168.56.10
PS> ssh sarais_ops@192.168.56.10
```

### 3.5 Endurecer SSH y activar el firewall
Ya conectado como `sarais_admin`:
```bash
VM$ cd /opt/sarais
VM$ sudo ./scripts/linux/harden_ssh.sh
VM$ sudo ./scripts/linux/setup_ufw.sh 192.168.56.0/24
```
Desde ahora `sysadmin` y `root` ya no pueden entrar por SSH, y nadie entra con contraseña.

### 3.6 Deploy key (git pull sin contraseña, solo lectura)
```bash
VM$ sudo -iu sarais_ops
VM$ ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N "" -C "sarais-vm"
VM$ cat ~/.ssh/github_deploy.pub
```
En GitHub: repositorio → **Settings → Deploy keys → Add deploy key**. Pega la llave y **no** marques "Allow write access".
```bash
VM$ printf 'Host github.com\n  IdentityFile ~/.ssh/github_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config
VM$ chmod 600 ~/.ssh/config
VM$ cd /opt/sarais
VM$ git remote set-url origin git@github.com:<ORG>/<REPO>.git
VM$ git pull                        # la 1.ª vez acepta la huella de github.com
```

### 3.7 Secretos (.env) de la VM
Sigue como `sarais_ops`:
```bash
VM$ cp .env.example .env && chmod 600 .env
VM$ nano .env
```
- Pon contraseñas **distintas** a las de desarrollo.
- **Quita el `#`** de la línea `COMPOSE_FILE=docker-compose.yaml`. Así la VM ignora el override y las bases de datos no se exponen.

### 3.8 Llave GPG de backups
La llave **privada** se queda en tu PC (y en una copia offline). La VM solo recibe la **pública**: si roban la VM, no pueden leer los backups.
```bash
PC$ gpg --quick-gen-key "sarais-backup@example.local" rsa3072 encrypt 2y
PC$ gpg --armor --export sarais-backup@example.local > backup_pub.asc
PC$ gpg --armor --export-secret-keys sarais-backup@example.local > backup_PRIVATE.asc   # guárdala fuera del repo
PC$ scp backup_pub.asc sarais_ops@192.168.56.10:/tmp/
VM$ gpg --import /tmp/backup_pub.asc && rm /tmp/backup_pub.asc
VM$ gpg --list-keys                 # debe aparecer sarais-backup@example.local
```

### 3.9 Certificado TLS, arranque y cron
```bash
VM$ exit                                        # vuelve a sarais_admin
VM$ cd /opt/sarais && sudo ./scripts/gen_certs.sh 192.168.56.10
VM$ sudo -iu sarais_ops
VM$ cd /opt/sarais && docker compose up -d --build
VM$ docker compose ps                           # 4 servicios "healthy"
VM$ crontab /opt/sarais/scripts/crontab.example
VM$ crontab -l
```
En Windows abre `https://192.168.56.10` y acepta el aviso del certificado.

---

## 4. Desplegar cambios (flujo de todos los días)

```bash
PC$ git add . && git commit -m "mensaje" && git push
PS> ssh sarais_ops@192.168.56.10
VM$ cd /opt/sarais
VM$ git pull
VM$ docker compose up -d --build     # reconstruye solo lo que cambió
VM$ docker compose ps
```
- Los datos viven en **volúmenes**. `git pull` y `up --build` no los borran.
- `ddl.sql` y `dml.sql` solo se ejecutan la **primera vez** (volumen vacío). Si cambias el esquema, haz un backup y luego `docker compose down -v && docker compose up -d`. **`-v` borra los datos.**
- No borres el volumen `sarais_mysql_keyring` por separado: sin esa llave, los datos cifrados de MySQL quedan ilegibles. Los backups no dependen de ella porque son lógicos (SQL) y van cifrados con GPG.

---

## 5. Verificación (resultado esperado)

| # | Prueba | Comando | Resultado esperado |
|---|---|---|---|
| 1 | Servicios sanos | `docker compose ps` | 4 servicios `Up (healthy)` |
| 2 | Usuario no root | `docker exec sarais_app id` · `docker exec mysql_db id` · `docker exec mongo_db id` · `docker exec sarais_nginx id` | uid=10001, 999, 999 y 101. Nunca `uid=0` |
| 3 | Puertos en la VM | `sudo ss -tlnp` | Solo 22 y 443 en 0.0.0.0. **No** aparecen 3306 ni 27017 |
| 4 | BD inalcanzables | `PS> Test-NetConnection 192.168.56.10 -Port 3306` | `TcpTestSucceeded : False` |
| 5 | TLS | En la VM: `openssl s_client -connect 127.0.0.1:443 </dev/null 2>/dev/null \| grep -E 'Protocol\|subject'` | `TLSv1.3` y `CN = 192.168.56.10` |
| 6 | Keyring de MySQL | `docker exec -it mysql_db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SELECT * FROM performance_schema.keyring_component_status"'` | `Component_status  Active` |
| 7 | Tablas cifradas | igual que 6 con `SELECT NAME, ENCRYPTION FROM information_schema.INNODB_TABLESPACES WHERE NAME LIKE 'sarais/%'` | `ENCRYPTION = Y` en todas |
| 8 | Mínimo privilegio | igual que 6, pero con `-u"$MYSQL_APP_USER" -p"$MYSQL_APP_PASSWORD"` y `DROP TABLE sarais.roles` | `ERROR 1142 ... DROP command denied` |
| 9 | Backup | `./scripts/backup.sh` | Termina en `Backup terminado correctamente`; crea `.gpg` + `.sha256` |
| 10 | Backup cifrado | `file /var/backups/sarais/*.gpg` · `zgrep -c CREATE /var/backups/sarais/*.gpg` | `PGP RSA encrypted session key` · `0` (no hay texto legible) |
| 11 | Restauración limpia | ver 5.1 | Aparece el cambio marcado |
| 12 | Checksum | agrega un byte a una copia del `.gpg` y restáurala | `El checksum NO coincide` y sale con error |
| 13 | Monitor | `./scripts/monitor.sh` | Línea CSV que termina en `OK` |
| 14 | Alerta | `docker stop mongo_db; ./scripts/monitor.sh; docker start mongo_db` | Termina en `ALERT:mongo` |
| 15 | Limpieza | `./scripts/cleanup.sh --dry-run` | Muestra `[dry-run]` y no borra nada |
| 16 | Cron | espera 5 min: `tail -n 2 /var/log/sarais/metrics/metrics_*.csv` | Hay una fila nueva |
| 17 | SSH root | `PS> ssh root@192.168.56.10` | `Permission denied (publickey)` |
| 18 | SSH con contraseña | `PS> ssh -o PubkeyAuthentication=no sarais_admin@192.168.56.10` | `Permission denied (publickey)` |
| 19 | Config SSH efectiva | `sudo sshd -T \| grep -E 'passwordauth\|permitroot'` | `passwordauthentication no` · `permitrootlogin no` |
| 20 | Firewall | `sudo ufw status verbose` | `Default: deny (incoming)` · `22/tcp LIMIT IN` · `443/tcp ALLOW IN` |
| 21 | Auditor | como `sarais_auditor`: `cat /var/log/sarais/backup.log` · `docker ps` · `cat /opt/sarais/.env` | Lee el log · `permission denied` · `Permission denied` |

### 5.1 Restaurar un backup en un entorno limpio
El entorno limpio es tu PC (WSL), porque ahí está la llave privada.
1. En la app de la VM, haz un cambio visible, por ejemplo una nota de un estudiante sintético. Anótalo.
2. `VM$ ./scripts/backup.sh`
3. Copia el backup a tu PC:
   ```bash
   PC$ scp 'sarais_ops@192.168.56.10:/var/backups/sarais/sarais_*' ~/sarais_backups/
   ```
4. Deja el entorno vacío y levántalo de nuevo (**borra los datos locales**):
   ```bash
   PC$ cd ~/sarais && docker compose down -v && docker compose up -d
   PC$ docker compose ps              # espera "healthy"
   ```
5. Restaura:
   ```bash
   PC$ ./scripts/restore.sh --yes ~/sarais_backups/sarais_<FECHA>.tar.gz.gpg
   ```
   Esperado: `Checksum SHA-256 correcto` → manifiesto → `MySQL restaurado: N tablas/vistas` → `MongoDB restaurado: audit_logs tiene N documentos` → `Restauración terminada`.
6. Entra a la app local: el cambio del paso 1 **debe** aparecer. Esa es la evidencia para el informe.

---

## 6. Problemas comunes

> Si desde WSL no llegas a `192.168.56.10` (`scp` o `ssh` se quedan esperando), haz la copia desde PowerShell (`PS> scp ...`). Luego, desde WSL, toma el archivo de `/mnt/c/Users/<tu_usuario>/`.


| Síntoma | Causa y solución |
|---|---|
| `mysql_db` reinicia y en el log aparece `keyring` | Revisa que exista el plugin dir: `docker run --rm sarais/mysql:8.4 mysqld --verbose --help \| grep plugin-dir`. Debe ser `/usr/lib64/mysql/plugin/`. Si es otro, cambia la ruta en `docker/mysql/Dockerfile` |
| Nginx: `cannot load certificate key` | Corre `sudo ./scripts/gen_certs.sh <IP>` (la llave debe tener el grupo 101) |
| `sarais_app` unhealthy | Falta `GET /health` en la app o la app no arranca: `docker logs sarais_app` |
| Init de MySQL falla en `05_users.sh` | Hay contraseñas con comillas o símbolos. Usa `openssl rand -hex 24` |
| `container name ... already in use` | `docker rm -f <nombre>` |
| SSH: `Permission denied (publickey)` con tu usuario | Usa la llave correcta: `ssh -i $env:USERPROFILE\.ssh\id_ed25519 ...`. Si te bloqueaste, entra por la consola de VirtualBox y borra `/etc/ssh/sshd_config.d/01-sarais-hardening.conf` |
| `backup.sh`: no está la llave pública | Repite 3.8 como **sarais_ops**: el keyring GPG es de cada usuario |
| `.env` con `\r` (editado en Windows) | `common.sh` ya lo limpia. Para Docker Compose usa `sed -i 's/\r$//' .env` |
