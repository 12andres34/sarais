#!/usr/bin/env bash
# setup_users.sh - Usuarios, grupos y permisos de Linux para SARAIS (en la VM).
# Es idempotente: se puede correr varias veces sin romper nada.
# Uso:  sudo ./scripts/linux/setup_users.sh [carpeta_con_llaves_publicas]
#   La carpeta (opcional) contiene <usuario>.pub, p. ej. sarais_admin.pub
#
# Diseño (mínimo privilegio):
#   Usuario          Grupos                        Para qué
#   sarais_admin     sudo, docker, sarais          administra el servidor
#   sarais_ops       docker, sarais, sarais-ops    despliega (git pull), corre cron/backups
#   sarais_auditor   sarais, sarais-audit          solo LEE logs y métricas
# OJO: el grupo docker equivale a root. Por eso el auditor NO está en él.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Ejecuta con sudo" >&2; exit 1; }

APP_DIR="${APP_DIR:-/opt/sarais}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/sarais}"
LOG_DIR="${LOG_DIR:-/var/log/sarais}"
KEYS_DIR="${1:-}"

log() { echo "$(date '+%F %T') [setup_users] $*"; }

# --- 1) Grupos ---
for g in sarais sarais-ops sarais-audit docker; do
  getent group "$g" >/dev/null || { groupadd "$g"; log "Grupo creado: $g"; }
done

# --- 2) Usuarios (shell bash, contraseña bloqueada: entran solo con llave SSH) ---
create_user() {
  local user="$1" groups="$2"
  if ! id "$user" >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash "$user"
    passwd -l "$user" >/dev/null     # sin contraseña => no hay login por contraseña
    log "Usuario creado: $user"
  fi
  usermod -aG "$groups" "$user"
  chmod 750 "/home/$user"

  # Carpeta .ssh con permisos estrictos (sshd rechaza permisos abiertos)
  install -d -m 700 -o "$user" -g "$user" "/home/$user/.ssh"
  touch "/home/$user/.ssh/authorized_keys"
  if [[ -n "$KEYS_DIR" && -f "$KEYS_DIR/$user.pub" ]]; then
    grep -qxF "$(cat "$KEYS_DIR/$user.pub")" "/home/$user/.ssh/authorized_keys" \
      || cat "$KEYS_DIR/$user.pub" >> "/home/$user/.ssh/authorized_keys"
    log "Llave pública instalada para $user"
  fi
  chown "$user:$user" "/home/$user/.ssh/authorized_keys"
  chmod 600 "/home/$user/.ssh/authorized_keys"
}
create_user sarais_admin   "sudo,docker,sarais"
create_user sarais_ops     "docker,sarais,sarais-ops"
create_user sarais_auditor "sarais,sarais-audit"

# --- 3) Carpeta del proyecto ---
# El código no es secreto (está en Git) y los contenedores (UID 999/101) deben
# poder leer los .sql y scripts de init montados: por eso "otros" pueden leer.
mkdir -p "$APP_DIR"
chown -R sarais_ops:sarais "$APP_DIR"
chmod -R u=rwX,g=rX,o=rX "$APP_DIR"
# setgid: lo nuevo hereda el grupo sarais
find "$APP_DIR" -type d -exec chmod g+s {} +
# Scripts: solo ops (dueño) y su grupo pueden ejecutarlos
find "$APP_DIR/scripts" -name '*.sh' -exec chmod 750 {} + 2>/dev/null || true
# .env tiene los secretos: solo el dueño
[[ -f "$APP_DIR/.env" ]] && chmod 600 "$APP_DIR/.env" && chown sarais_ops:sarais_ops "$APP_DIR/.env"
# La carpeta de certificados la maneja gen_certs.sh (grupo 101 = nginx)

# --- 4) Backups: solo sarais_ops ---
install -d -m 700 -o sarais_ops -g sarais_ops "$BACKUP_DIR"

# --- 5) Logs: escribe ops, lee el auditor (setgid para heredar el grupo) ---
install -d -m 2750 -o sarais_ops -g sarais-audit "$LOG_DIR"
install -d -m 2750 -o sarais_ops -g sarais-audit "$LOG_DIR/metrics"

# --- 6) Resumen ---
log "Resultado:"
for u in sarais_admin sarais_ops sarais_auditor; do echo "  $(id "$u")"; done
ls -ld "$APP_DIR" "$BACKUP_DIR" "$LOG_DIR" "$LOG_DIR/metrics" | sed 's/^/  /'
log "Siguiente paso: asigna una contraseña SOLO para sudo a sarais_admin: sudo passwd sarais_admin"
