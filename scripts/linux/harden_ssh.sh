#!/usr/bin/env bash
# harden_ssh.sh - Endurece OpenSSH: sin contraseñas, sin root, solo llaves.
# Uso:  sudo ./scripts/linux/harden_ssh.sh
# ANTES: comprueba que ya entras con llave (ssh -i ...). Deja otra sesión abierta.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Ejecuta con sudo" >&2; exit 1; }

# Se llama 01-... para que se lea ANTES que 50-cloud-init.conf:
# en sshd gana el PRIMER valor que encuentra para cada opción.
CONF=/etc/ssh/sshd_config.d/01-sarais-hardening.conf
ALLOWED_GROUP=sarais

log() { echo "$(date '+%F %T') [harden_ssh] $*"; }

# Seguridad: no aplicar si nadie del grupo tiene una llave instalada (te dejarías fuera)
has_key=false
for u in $(getent group "$ALLOWED_GROUP" | cut -d: -f4 | tr ',' ' '); do
  [[ -s "/home/$u/.ssh/authorized_keys" ]] && has_key=true && log "Llave encontrada para $u"
done
$has_key || { log "ERROR: ningún usuario del grupo $ALLOWED_GROUP tiene llave. No se aplica."; exit 1; }

# Respaldo de la configuración anterior (si existía)
[[ -f "$CONF" ]] && cp -p "$CONF" "$CONF.bak.$(date +%s)"

cat > "$CONF" <<EOF
# SARAIS - endurecimiento de SSH (generado por harden_ssh.sh)
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
PubkeyAuthentication yes
AuthenticationMethods publickey
AllowGroups $ALLOWED_GROUP
MaxAuthTries 3
LoginGraceTime 30
MaxSessions 4
X11Forwarding no
AllowAgentForwarding no
PermitTunnel no
ClientAliveInterval 300
ClientAliveCountMax 2
LogLevel VERBOSE
EOF
chmod 644 "$CONF"

# Validar ANTES de recargar: si hay error, se revierte
if ! sshd -t; then
  log "ERROR: configuración inválida, se elimina $CONF"
  rm -f "$CONF"
  exit 1
fi

systemctl reload ssh
log "SSH recargado. Valores efectivos:"
sshd -T | grep -Ei '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication|authenticationmethods|allowgroups|maxauthtries) '
