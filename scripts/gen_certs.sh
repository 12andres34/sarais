#!/usr/bin/env bash
# gen_certs.sh - Certificado TLS autofirmado para Nginx (válido 365 días).
# Uso:  sudo ./scripts/gen_certs.sh [IP_o_nombre]     (por defecto 192.168.56.10)
# Crea docker/nginx/certs/sarais.crt y sarais.key (la llave NUNCA va a Git).
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
init_logging
require_cmd openssl

[[ $EUID -eq 0 ]] || die "Ejecuta con sudo (hay que dar la llave al usuario de Nginx, UID 101)"

HOST="${1:-192.168.56.10}"
CERT_DIR="$PROJECT_DIR/docker/nginx/certs"
NGINX_UID=101   # usuario de la imagen nginx-unprivileged
mkdir -p "$CERT_DIR"

# SAN: el navegador exige el nombre/IP aquí, no solo en el CN
if [[ "$HOST" =~ ^[0-9.]+$ ]]; then SAN="IP:$HOST,DNS:localhost,IP:127.0.0.1"
else SAN="DNS:$HOST,DNS:localhost,IP:127.0.0.1"; fi

openssl req -x509 -nodes -newkey rsa:3072 -sha256 -days 365 \
  -keyout "$CERT_DIR/sarais.key" -out "$CERT_DIR/sarais.crt" \
  -subj "/C=CO/ST=Boyaca/L=Tunja/O=SARAIS Demo/CN=$HOST" \
  -addext "subjectAltName=$SAN" 2>/dev/null

# Permisos: llave legible solo por root y el grupo de Nginx
chown "root:$NGINX_UID" "$CERT_DIR/sarais.key"
chmod 640 "$CERT_DIR/sarais.key"
chmod 644 "$CERT_DIR/sarais.crt"
chgrp "$NGINX_UID" "$CERT_DIR"
chmod 750 "$CERT_DIR"

log INFO "Certificado creado para $HOST:"
openssl x509 -in "$CERT_DIR/sarais.crt" -noout -subject -enddate -ext subjectAltName
