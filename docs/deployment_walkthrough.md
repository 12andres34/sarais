# SARAIS – Guía de despliegue paso a paso

Guía detallada para desplegar SARAIS por primera vez, pensada para quien no ha administrado un servidor. La referencia técnica resumida es `docs/deployment_vm.md`. Cada paso indica:

- **Dónde:** en qué ventana trabajar.
- **Comando:** lo que se escribe. Se pega **completo** y se presiona **Enter**.
- **Resultado esperado:** lo que debe salir.
- **Si falla:** qué revisar si sale otra cosa.

**No te saltes pasos ni cambies el orden.** Si un resultado no coincide, detente y consulta `docs/troubleshooting.md`.

Tiempo total: unas 3 horas. Puedes partirlo en 2 o 3 días: al final de cada parte puedes apagar todo y seguir otro día.

---

## Antes de empezar: las 4 ventanas que vas a usar

| Ventana | Cómo se abre | Para qué |
|---|---|---|
| **VirtualBox** | Menú Inicio → VirtualBox | Crear la máquina virtual. Su pantalla negra solo la usas en la Parte 1 |
| **Ubuntu (WSL)** | Menú Inicio → escribe *Ubuntu* | **Tu ventana principal.** Desde aquí entras a la VM |
| **PowerShell** | Menú Inicio → escribe *PowerShell* | Solo para 2 pasos |
| **Navegador** | Chrome o Edge | Para probar la página al final |

### Cómo saber "dónde estoy"
Mira el texto que aparece antes del cursor (se llama *prompt*):

| Si ves… | Estás en… |
|---|---|
| `tu_usuario@TU-PC:~$` | Ubuntu de WSL (tu computador) |
| `sysadmin@sarais-vm:~$` | La VM, como el usuario de instalación |
| `sarais_admin@sarais-vm:~$` | La VM, como administrador |
| `sarais_ops@sarais-vm:~$` | La VM, como operador (Docker y backups) |
| `PS C:\Users\...>` | PowerShell de Windows |

### 4 trucos que te ahorran problemas
1. **Pegar en Ubuntu (WSL):** clic derecho, o `Ctrl+Shift+V`. (`Ctrl+V` no funciona.)
2. **Pegar en PowerShell:** clic derecho.
3. **Las contraseñas no se ven mientras las escribes.** Ni puntos ni asteriscos. Es normal: escríbela y presiona Enter.
4. **Volver a tu computador desde la VM:** escribe `exit` y Enter.

---

# PARTE 0 – Publicar la versión en GitHub (10 min)

La VM descarga el código desde GitHub: solo recibe lo que esté publicado.

**Paso 0.1 – Revisa y sube los cambios**

**Dónde:** Abre **Ubuntu (WSL)**.

**Comando:**
```bash
cd ~/proyecto_integrador
git status --short
```
**Resultado esperado:** Solo aparecen archivos del proyecto. **No** deben aparecer `.env`, `.env.*` (salvo `.env.example`), ni archivos `.pem`, `.key` o `.zip`.

**Si falla:** Si aparece alguno, **no sigas**: revisa `.gitignore`.

**Comando:**
```bash
git add -A
git commit -m "chore: preparar despliegue en la VM"
git push
```
**Resultado esperado:** Al final debes ver algo como `main -> main`.

**Paso 0.2 – Anota la dirección de tu repositorio**

**Dónde:** En el navegador, abre tu repositorio en GitHub → botón verde **Code** → pestaña **HTTPS** → copia la dirección. Es algo como `https://github.com/usuario/proyecto_integrador.git`.

Si el repositorio es **privado**, GitHub te pedirá un *token* al descargarlo. Créalo así:
1. GitHub → tu foto (arriba a la derecha) → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
2. En *Repository access*, elige **Only select repositories** y marca tu repositorio.
3. En *Permissions*, busca **Contents** y ponlo en **Read-only**.
4. Haz clic en **Generate token** y cópialo en un lugar seguro. Solo se muestra una vez.

---

# PARTE 1 – Crear la máquina virtual (40 min)

**Paso 1.1 – Descarga Ubuntu Server**

**Dónde:** En el navegador, abre `https://ubuntu.com/download/server` → busca **Ubuntu Server 22.04 LTS** → descarga el archivo `.iso` (pesa unos 2 GB).

Si en la página principal solo aparece la versión más nueva, busca "22.04" en esa misma página, en la sección de versiones anteriores. **Tiene que ser la 22.04.**

**Paso 1.2 – Revisa la red "solo-anfitrión"**

**Dónde:** VirtualBox → menú **Archivo** → **Herramientas** → **Administrador de red** → pestaña **Host-only Networks**.

**Resultado esperado:** Debe haber una red con `192.168.56.1/24`. Si no hay ninguna, haz clic en **Crear**.

**Paso 1.3 – Crea la VM**

**Dónde:** VirtualBox → botón **Nueva**.

1. **Nombre:** `sarais-vm`
2. **Imagen ISO:** elige el `.iso` que descargaste.
3. ✔ Marca **"Omitir instalación desatendida"** (*Skip Unattended Installation*). Si no la marcas, VirtualBox instala Ubuntu solo y con otras opciones.
4. **Memoria:** `4096 MB`. **Procesadores:** `2`.
5. **Disco:** `25 GB`.
6. Clic en **Terminar**.

**Paso 1.4 – Agrega la segunda tarjeta de red**

**Dónde:** Selecciona `sarais-vm` → **Configuración** → **Red**.
- **Adaptador 1:** déjalo como está (**NAT**). Es la salida a Internet.
- **Adaptador 2:** ✔ **Habilitar** → *Conectado a:* **Adaptador solo-anfitrión** (*Host-only Adapter*). Es el que conecta tu PC con la VM.

Clic en **Aceptar**.

**Paso 1.5 – Instala Ubuntu**

**Dónde:** Selecciona `sarais-vm` → **Iniciar**. Se abre una pantalla negra.

Dentro del instalador, el mouse no sirve: se usan las **flechas**, **Tab**, **Espacio** (marcar) y **Enter** (aceptar).

| Pantalla | Qué elegir |
|---|---|
| Language | **English** (los errores en inglés son más fáciles de buscar) |
| Keyboard | Layout: **Spanish (Latin American)** |
| Type of install | **Ubuntu Server** (no el *minimized*) |
| **Network connections** | ⚠️ **Ver el recuadro de abajo** |
| Proxy | Vacío → Done |
| Mirror | Déjalo como está → Done |
| Storage | **Use an entire disk**. ⚠️ **Quita** la marca de **"Set up this disk as an LVM group"** (con Espacio). Si la dejas, Ubuntu usa solo la mitad del disco |
| Confirm | **Continue** |
| Profile | Your name: `sysadmin` · Server name: `sarais-vm` · Username: `sysadmin` · Password: una contraseña que **no olvides** (anótala) |
| Ubuntu Pro | **Skip for now** |
| SSH | ✔ **Install OpenSSH server**. No importes llaves |
| Featured snaps | No marques nada → Done |

> **⚠️ Network connections (la IP fija 192.168.56.10)**
> Vas a ver dos tarjetas: `enp0s3` (con `10.0.2.15`) y `enp0s8`.
> 1. Baja con las flechas hasta **enp0s8** → Enter → **Edit IPv4**.
> 2. *IPv4 Method:* **Manual**.
> 3. **Subnet:** `192.168.56.0/24`
> 4. **Address:** `192.168.56.10`
> 5. **Gateway**, **Name servers** y **Search domains**: **vacíos**.
> 6. **Save** → **Done**.
>
> **Resultado esperado:** `enp0s8` debe decir `static 192.168.56.10/24`.
> No toques `enp0s3`: debe seguir en DHCP.

Espera a que termine (10–15 min). Cuando diga **Reboot Now**, presiónalo. Si dice *"Please remove the installation medium"*, presiona Enter.

**Paso 1.6 – Primer inicio de sesión (en la pantalla negra)**

**Resultado esperado:** Debes ver `sarais-vm login:`.

**Comando:** Escribe `sysadmin`, Enter, y luego la contraseña (no se ve), Enter.

**Resultado esperado:** Debes ver `sysadmin@sarais-vm:~$`.

**A partir de aquí no vuelves a escribir en esta pantalla negra**: en ella no se puede pegar. Puedes minimizarla, pero **no la cierres**.

---

# PARTE 2 – Conectarte desde tu PC e instalar Docker (20 min)

**Paso 2.1 – ¿Tu PC ve la VM?**

**Dónde:** **Ubuntu (WSL)**

**Comando:**
```bash
ping -c 3 192.168.56.10
```
**Resultado esperado:** Debes ver 3 líneas `64 bytes from 192.168.56.10`.

**Si falla:** Si sale `100% packet loss`, prueba lo mismo en **PowerShell**: `ping 192.168.56.10`.
- Si en PowerShell sí responde, WSL no llega a la VM: usa PowerShell para entrar a la VM.
- Si tampoco responde, revisa el Paso 1.4 (Adaptador 2) y el recuadro de red del Paso 1.5.

**Paso 2.2 – Entra a la VM por SSH**

**Comando:** (en WSL)
```bash
ssh sysadmin@192.168.56.10
```
- La primera vez pregunta `Are you sure you want to continue connecting (yes/no)?` → escribe `yes` y Enter.
- Luego pide la contraseña de `sysadmin`.

**Resultado esperado:** El prompt cambia a `sysadmin@sarais-vm:~$`. **Ya estás dentro de la VM, y desde aquí sí puedes pegar.**

**Paso 2.3 – Hora correcta (sin ella, los códigos MFA no funcionan)**

**Comando:**
```bash
sudo timedatectl set-timezone America/Bogota
timedatectl
```
- `sudo` pide la contraseña de `sysadmin`.

**Resultado esperado:** Debes ver `Time zone: America/Bogota` y `System clock synchronized: yes`.

**Si falla:** Si dice `no`, espera 2 minutos y repite `timedatectl`.

**Paso 2.4 – ¿La VM puede correr MongoDB?**

**Comando:**
```bash
grep -o -m1 -w avx /proc/cpuinfo
```
**Resultado esperado:** Debe imprimir `avx`.

**Si falla:** Si no imprime nada, **detente**: MongoDB 7 no arrancará en esta VM (ver Hyper-V / AVX en `docs/troubleshooting.md`).

**Paso 2.5 – Actualiza Ubuntu (5–10 min)**

**Comando:**
```bash
sudo apt-get update && sudo apt-get -y upgrade
sudo apt-get install -y ca-certificates curl git gnupg rsync
```
**Resultado esperado:** Termina sin la palabra `E:` (error). Si aparece una ventana morada preguntando por servicios, presiona Enter.

**Paso 2.6 – Instala Docker**

Pega **línea por línea** y espera a que cada una termine:
```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```
**Comando:** Comprueba:
```bash
sudo docker run --rm hello-world
docker compose version
```
**Resultado esperado:** Debes ver `Hello from Docker!` y `Docker Compose version v2...`.

---

# PARTE 3 – Usuarios, llaves SSH y firewall (30 min)

Vamos a crear 3 usuarios (`sarais_admin`, `sarais_ops`, `sarais_auditor`) que entran **solo con llave**, sin contraseña.

**Paso 3.1 – Crea tu llave en WSL**

**Dónde:** Abre **otra pestaña** de Ubuntu (WSL). En la ventana de Ubuntu hay un **+** arriba; si no lo hay, abre Ubuntu otra vez desde el menú Inicio.

**Comando:**
```bash
ls ~/.ssh/id_ed25519.pub
```
- Si dice `No such file`, créala:
```bash
ssh-keygen -t ed25519 -C "mi-wsl"
```
Presiona Enter en la ruta. Luego escribe una **frase de paso** dos veces (anótala).

**Comando:** Envíala a la VM:
```bash
scp ~/.ssh/id_ed25519.pub sysadmin@192.168.56.10:/tmp/wsl.pub
```
**Resultado esperado:** Pide la contraseña de `sysadmin` y muestra `100%`.

**Paso 3.2 – Crea una llave en Windows (para probar SSH desde Windows)**

**Dónde:** **PowerShell**

**Comando:**
```powershell
ssh-keygen -t ed25519 -C "mi-windows"
scp $env:USERPROFILE\.ssh\id_ed25519.pub sysadmin@192.168.56.10:/tmp/win.pub
```
**Resultado esperado:** `100%`.

**Si falla:** Si `ssh-keygen` dice que el archivo ya existe y pregunta *Overwrite*, escribe `n`: ya tienes una llave y sirve esa.

**Paso 3.3 – Descarga el proyecto en la VM**

**Dónde:** Vuelve a la pestaña donde está `sysadmin@sarais-vm:~$`.

**Comando:** Cambia la dirección por la tuya (Paso 0.3):
```bash
sudo git clone https://github.com/USUARIO/REPO.git /opt/sarais
sudo git config --system --add safe.directory /opt/sarais
```
- Si el repo es privado: en *Username* escribe tu usuario de GitHub, y en *Password* pega el **token** (clic derecho). No se ve.

**Resultado esperado:** `Receiving objects: 100%`.

**Paso 3.4 – Crea los usuarios**

**Comando:**
```bash
mkdir -p /tmp/keys
cat /tmp/wsl.pub /tmp/win.pub > /tmp/keys/sarais_admin.pub
cp /tmp/wsl.pub /tmp/keys/sarais_ops.pub
cp /tmp/wsl.pub /tmp/keys/sarais_auditor.pub
cd /opt/sarais
sudo ./scripts/linux/setup_users.sh /tmp/keys
```
**Resultado esperado:** El script termina sin `ERROR`.

**Comando:** Dale una contraseña a `sarais_admin`. **Solo la usará para `sudo`, no para entrar.** Anótala:
```bash
sudo passwd sarais_admin
rm -rf /tmp/keys /tmp/*.pub
```

**Paso 3.5 – Prueba que las llaves funcionan (¡antes de cerrar SSH!)**

**Dónde:** **No cierres** la pestaña de `sysadmin`. En la **otra** pestaña de WSL:

**Comando:**
```bash
ssh sarais_admin@192.168.56.10
```
**Resultado esperado:** Entra **sin pedir la contraseña de la VM**. Solo te pide la *frase de paso* de tu llave, si le pusiste una. El prompt es `sarais_admin@sarais-vm:~$`.

**Si falla:** Si pide `sarais_admin@192.168.56.10's password:`, la llave no quedó. **No sigas**: revisa `docs/troubleshooting.md`.

**Paso 3.6 – Cierra la entrada con contraseña y activa el firewall**

**Dónde:** En la pestaña de `sarais_admin@sarais-vm`:

**Comando:**
```bash
cd /opt/sarais
sudo ./scripts/linux/harden_ssh.sh
sudo ./scripts/linux/setup_ufw.sh 192.168.56.0/24
sudo ufw status
```
**Resultado esperado:** `Status: active`, con `22/tcp LIMIT` y `443/tcp ALLOW`.

**Paso 3.7 – Comprueba**

**Dónde:** En la pestaña de `sysadmin`, escribe `exit`. Luego, en WSL:

**Comando:**
```bash
ssh sysadmin@192.168.56.10
```
**Resultado esperado:** `Permission denied`. **Es correcto:** ahora solo entran los usuarios de SARAIS, y solo con llave.

**Comando:**
```bash
ssh sarais_ops@192.168.56.10
```
**Resultado esperado:** Entras como `sarais_ops@sarais-vm:~$`.

> Si algún día te quedas por fuera: ve a la **pantalla negra de VirtualBox**, entra como `sysadmin` con su contraseña y escribe:
> `sudo rm /etc/ssh/sshd_config.d/01-sarais-hardening.conf && sudo systemctl reload ssh`

**Fin de la Parte 3.** Si quieres parar aquí: ve a la pantalla negra de VirtualBox y apaga con `sudo shutdown now`.

---

# PARTE 4 – Crear los secretos (`.env`) (5 min)

**Dónde:** WSL → `ssh sarais_ops@192.168.56.10`

**Comando:**
```bash
cd /opt/sarais
./scripts/gen_env.sh
```
**Resultado esperado:** Al final debe decir `[OK] puertos publicados: solo 443` y `.env válido`.

**No abras el `.env` con nano.** El script ya puso contraseñas nuevas y seguras.

---

# PARTE 5 – Llaves GPG para cifrar backups y documentos (15 min)

**Paso 5.1 – Créalas en tu PC (WSL), no en la VM**

**Dónde:** Una pestaña de WSL **en tu PC** (prompt `tu_usuario@TU-PC`). Si estás en la VM, escribe `exit`.

**Comando:**
```bash
export GPG_TTY=$(tty)
gpg --quick-gen-key "SARAIS VM Backup <sarais-vm-backup@example.local>" rsa3072 encrypt 2y
```
Te pide una **frase de paso** (dos veces). Anótala: sin ella no podrás abrir los backups.

**Comando:**
```bash
gpg --quick-gen-key "SARAIS VM Docs <sarais-vm-docs@example.local>" rsa3072 encrypt 2y
```

**Paso 5.2 – Muestra las huellas**

**Comando:**
```bash
BK=$(gpg --list-keys --with-colons sarais-vm-backup@example.local | awk -F: '/^fpr/{print $10; exit}')
DK=$(gpg --list-keys --with-colons sarais-vm-docs@example.local | awk -F: '/^fpr/{print $10; exit}')
echo "BACKUP=$BK"
echo "DOCS=$DK"
```
**Resultado esperado:** Dos líneas, cada una con 40 letras y números. **Cópialas** a un bloc de notas.

**Paso 5.3 – Guarda las llaves**

**Comando:**
```bash
mkdir -p ~/sarais_keys && chmod 700 ~/sarais_keys
gpg --armor --export "$BK" > ~/sarais_keys/backup_pub.asc
gpg --armor --export "$DK" > ~/sarais_keys/docs_pub.asc
gpg --armor --export-secret-keys "$BK" "$DK" > ~/sarais_keys/PRIVATE_vm_keys.asc
chmod 600 ~/sarais_keys/*
scp ~/sarais_keys/backup_pub.asc ~/sarais_keys/docs_pub.asc sarais_ops@192.168.56.10:/tmp/
```
**Resultado esperado:** `100%` dos veces.

- `PRIVATE_vm_keys.asc` es la llave privada. Cópiala a una USB y **nunca** la subas a la VM ni a GitHub.
- Solo enviamos a la VM las llaves **públicas** (`_pub.asc`).

**Paso 5.4 – Impórtalas en la VM**

**Dónde:** WSL → `ssh sarais_ops@192.168.56.10`

**Comando:**
```bash
install -d -m 700 ~/keys
mv /tmp/backup_pub.asc /tmp/docs_pub.asc ~/keys/
gpg --import ~/keys/backup_pub.asc
cd /opt/sarais
```
**Comando:** Pega tus huellas en lugar de `HUELLA_...` (las del Paso 5.2):
```bash
./scripts/gen_env.sh --set BACKUP_GPG_RECIPIENT=HUELLA_BACKUP --set DOCS_GPG_RECIPIENT=HUELLA_DOCS
```
**Resultado esperado:** `Variable actualizada` dos veces y `.env válido`.

---

# PARTE 6 – Certificados y revisión final (10 min)

**Dónde:** WSL → `ssh sarais_admin@192.168.56.10` (necesitas `sudo`; si estás como `sarais_ops`, primero `exit`).

**Comando:**
```bash
cd /opt/sarais
sudo ./scripts/gen_certs.sh 192.168.56.10
sudo ./scripts/gen_mysql_certs.sh
sudo ./scripts/preflight.sh
```
`sudo` pide la contraseña de `sarais_admin` (Paso 3.4).

**Resultado esperado:** La última línea debe decir `Resultado: N PASS, 0 FAIL`.

**Si falla:** Si hay algún `FAIL`, **no sigas**. Copia el mensaje completo y mándamelo.

---

# PARTE 7 – Arrancar SARAIS (15 min)

**Dónde:** Escribe `exit` → `ssh sarais_ops@192.168.56.10`

**Paso 7.1 – Construye y arranca (la primera vez tarda 5–10 min)**

**Comando:**
```bash
cd /opt/sarais
docker compose up -d --build
```
**Resultado esperado:** Al final: `Container ... Started` o `Healthy`.

**Paso 7.2 – Espera a que todo esté "sano"**

**Comando:**
```bash
docker compose ps
```
**Resultado esperado:** Los **4** (`mysql_db`, `mongo_db`, `sarais_app`, `sarais_nginx`) dicen `(healthy)`. Si dice `(health: starting)`, espera 1 minuto y repite.

**Si falla:** Si alguno dice `Restarting` o `Exited`, mira sus mensajes con `docker logs mongo_db --tail 30` (cambia el nombre por el del contenedor que falla) y mándamelos.

**Paso 7.3 – Tres ajustes después del primer arranque**

**Comando:** Protege la llave maestra de MySQL:
```bash
docker exec mysql_db chmod 600 /var/lib/mysql-keyring/component_keyring_file
```
**Comando:** Pon la llave pública de documentos dentro de la app:
```bash
docker exec -i sarais_app gpg --batch --import < ~/keys/docs_pub.asc
```
**Resultado esperado:** `imported: 1`.

**Comando:** Crea las contraseñas de las cuentas demo. Escribe una contraseña de 12 o más caracteres, **distinta** a la de desarrollo, y anótala:
```bash
read -rs -p "Contraseña demo: " SEED_PASSWORD; echo; export SEED_PASSWORD
docker exec -e SEED_PASSWORD sarais_app python -m app.scripts.seed_data --allow-production
unset SEED_PASSWORD
```
**Resultado esperado:** `[seed] Hashes reemplazados: 17` y una tabla con los usuarios.

**Paso 7.4 – Verificación**

**Comando:**
```bash
./scripts/verify_encryption.sh
```
**Resultado esperado:** Al final: `0 FAIL`.

---

# PARTE 8 – Entrar desde Windows (10 min)

**Paso 8.1 – Abre la página**

**Dónde:** **Navegador** → `https://192.168.56.10`

1. Sale **"La conexión no es privada"**. Es normal: el certificado es autofirmado.
2. Clic en **Configuración avanzada** → **Continuar a 192.168.56.10**.

**Resultado esperado:** Ves la pantalla de login de SARAIS.

**Paso 8.2 – Entra como docente**

1. Usuario `lgomez` y la contraseña demo del Paso 7.3.
2. Aparece un **QR**. Ábrelo con *Google Authenticator* o *Microsoft Authenticator* en tu celular → **+** → **Escanear código QR**.
3. Escribe el código de 6 dígitos que muestra el celular.

**Resultado esperado:** Ves el panel del docente.

**Paso 8.3 – Entra como estudiante**

**Dónde:** Abre una **ventana de incógnito** (`Ctrl+Shift+N`) → `https://192.168.56.10`

1. Usuario `est.sofia.r` y la misma contraseña demo.
2. Escanea **su propio** QR y escribe el código.

**Resultado esperado:** Ves el boletín de Sofía.

**Paso 8.4 – SSH desde Windows**

**Dónde:** **PowerShell**

**Comando:**
```powershell
ssh sarais_admin@192.168.56.10
```
**Resultado esperado:** Entra con tu llave de Windows. Escribe `exit` para salir.

🎉 **SARAIS ya está desplegado.**

---

# PARTE 9 – Tareas automáticas y primer backup (10 min)

**Dónde:** WSL → `ssh sarais_ops@192.168.56.10`

**Comando:**
```bash
cd /opt/sarais
crontab scripts/crontab.example
crontab -l
./scripts/backup.sh
ls -l /var/backups/sarais/
```
**Resultado esperado:** `crontab -l` muestra 3 tareas: backup diario, monitoreo cada 5 minutos y limpieza semanal. `backup.sh` termina con `Backup terminado correctamente`. `ls` muestra un archivo `.gpg` y otro `.sha256`.

Desde ahora, la VM toma una medición de recursos cada 5 minutos (monitoreo y alertas). Las métricas del informe se toman por **escenarios** (reposo 30 min, uso 15 min, backup): ver `docs/deployment_vm.md` §8.1. No hace falta dejarla 24 horas.

---

# Cómo apagar y volver a encender

**Apagar:** WSL → `ssh sarais_admin@192.168.56.10` → `sudo shutdown now`.

**Encender otro día:**
1. VirtualBox → selecciona `sarais-vm` → flecha junto a **Iniciar** → **Inicio sin interfaz** (*Headless*). Así no se abre la pantalla negra.
2. Espera 2 minutos. Docker vuelve a arrancar SARAIS **solo**.
3. Comprueba con `ssh sarais_ops@192.168.56.10` → `cd /opt/sarais && docker compose ps` (los 4 en `healthy`).

---

# Reglas que nunca debes romper

1. **Nunca** escribas `docker compose down -v` en la VM. Borra la llave maestra de MySQL y **se pierden todos los datos**.
2. **Nunca** subas la llave privada GPG (`PRIVATE_vm_keys.asc`) a la VM ni a GitHub.
3. **Nunca** edites el `.env` con nano ni desde Windows. Para cambiar algo: `./scripts/gen_env.sh --set CLAVE=VALOR`.
4. Escribe los comandos **siempre desde `/opt/sarais`** (`cd /opt/sarais`).
5. Guarda en un lugar seguro: la contraseña de `sysadmin`, la de `sarais_admin`, la contraseña demo, las frases de paso de tus llaves SSH y GPG, y la USB con la llave privada.

---

# Qué sigue

Cuando esto funcione, sigue en `docs/deployment_vm.md`:
- **Sección 7.3:** probar que un backup se puede restaurar (en WSL).
- **Sección 8:** tabla y gráfica de métricas para el informe.
- **Sección 9:** las pruebas y la lista de capturas de evidencia (índice en `docs/evidence/README.md`).

---

## Justificación técnica
- **Para qué son las dos tarjetas de red:** NAT da Internet a la VM. Solo-anfitrión une tu PC y la VM con la IP fija `192.168.56.10`.
- **Por qué se entra por SSH y no por la pantalla negra:** se puede pegar, es lo que se usa con servidores reales y la conexión va cifrada.
- **Por qué probamos la llave antes de `harden_ssh.sh`:** ese script apaga la entrada con contraseña. Si la llave fallara, quedarías por fuera.
- **Para qué es cada usuario:** `sarais_admin` administra (sudo). `sarais_ops` maneja Docker y los backups. `sarais_auditor` solo lee los logs.
- **Por qué los certificados van antes de `docker compose up`:** si falta `ca.pem`, Docker crea una carpeta con ese nombre y MySQL no arranca.
- **Por qué el navegador avisa "no es privada" y aun así la conexión va cifrada:** el aviso dice que nadie reconocido firmó el certificado, no que falte cifrado.

---

Si algo falla, consulta **`docs/troubleshooting.md`**.
