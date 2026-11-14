#!/usr/bin/env bash
# setup_ufw.sh - Firewall: todo cerrado de entrada, excepto SSH y HTTPS.
# Uso:  sudo ./scripts/linux/setup_ufw.sh [red_permitida_para_SSH]
#   Ej.: sudo ./scripts/linux/setup_ufw.sh 192.168.56.0/24
#   Sin argumento, SSH se permite desde cualquier origen (con límite de intentos).
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Ejecuta con sudo" >&2; exit 1; }
command -v ufw >/dev/null || apt-get install -y ufw

SSH_FROM="${1:-}"
log() { echo "$(date '+%F %T') [setup_ufw] $*"; }

ufw --force reset >/dev/null           # empezar desde cero (idempotente)
ufw default deny incoming
ufw default allow outgoing

# SSH: "limit" bloquea una IP con 6+ conexiones en 30 s (frena fuerza bruta)
if [[ -n "$SSH_FROM" ]]; then
  ufw limit from "$SSH_FROM" to any port 22 proto tcp comment 'SSH admin'
else
  ufw limit 22/tcp comment 'SSH admin'
fi

# HTTPS (Nginx)
ufw allow 443/tcp comment 'HTTPS SARAIS'

ufw logging low
ufw --force enable
log "UFW activo:"
ufw status verbose

cat <<'EOF'

AVISO: Docker escribe sus propias reglas de iptables y los puertos PUBLICADOS
por un contenedor NO pasan por UFW. Por eso en la VM:
  - solo se publica 443 (docker-compose.yaml),
  - las bases de datos no tienen "ports:" (el override de desarrollo no se usa).
Compruébalo con:  sudo ss -tlnp   (no deben aparecer 3306 ni 27017)
EOF
