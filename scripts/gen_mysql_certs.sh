#!/usr/bin/env bash
# gen_mysql_certs.sh - CA interna + certificado TLS de MySQL (app -> mysql_db cifrado y verificado).
# Uso:  sudo ./scripts/gen_mysql_certs.sh        (FORCE=1 para regenerar)
# Crea:
#   docker/mysql/certs/ca.pem            público  -> se monta en mysql_db y en la app
#   docker/mysql/certs/server-cert.pem   público
#   docker/mysql/certs/server-key.pem    privado  -> dueño UID 999 (usuario mysql de la imagen), 600
#   docker/mysql/ca-private/ca-key.pem   privado  -> NO se monta en ningún contenedor
# Ninguno va a Git (.gitignore).
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
init_logging
require_cmd openssl

[[ $EUID -eq 0 ]] || die "Ejecuta con sudo (hay que dar la llave al usuario mysql, UID ${MYSQL_UID:-999})"

CERT_DIR="$PROJECT_DIR/docker/mysql/certs"
CA_DIR="$PROJECT_DIR/docker/mysql/ca-private"
MYSQL_UID="${MYSQL_UID:-999}"   # compruébalo: docker exec mysql_db id -u
# Nombres con los que se conecta la app (MYSQL_HOST=mysql_db) y Workbench (127.0.0.1)
SAN="DNS:mysql_db,DNS:localhost,IP:127.0.0.1"

if [[ -f "$CERT_DIR/server-cert.pem" && "${FORCE:-0}" != "1" ]]; then
  log INFO "Ya existen certificados en $CERT_DIR (usa FORCE=1 para regenerar)"; exit 0
fi

umask 077
mkdir -p "$CERT_DIR" "$CA_DIR"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# 1) CA interna (10 años)
openssl req -x509 -new -newkey rsa:3072 -nodes -sha256 -days 3650 \
  -keyout "$CA_DIR/ca-key.pem" -out "$CERT_DIR/ca.pem" \
  -subj "/C=CO/O=SARAIS Demo/CN=SARAIS Internal MySQL CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null

# 2) Llave y solicitud del servidor
openssl req -new -newkey rsa:3072 -nodes -sha256 \
  -keyout "$CERT_DIR/server-key.pem" -out "$TMP/server.csr" \
  -subj "/C=CO/O=SARAIS Demo/CN=mysql_db" 2>/dev/null

cat > "$TMP/ext.cnf" <<EOF
basicConstraints=CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=$SAN
EOF

# 3) La CA firma el certificado del servidor (825 días)
openssl x509 -req -in "$TMP/server.csr" -CA "$CERT_DIR/ca.pem" -CAkey "$CA_DIR/ca-key.pem" \
  -CAcreateserial -CAserial "$TMP/ca.srl" -days 825 -sha256 \
  -extfile "$TMP/ext.cnf" -out "$CERT_DIR/server-cert.pem" 2>/dev/null

openssl verify -CAfile "$CERT_DIR/ca.pem" "$CERT_DIR/server-cert.pem" >/dev/null \
  || die "El certificado no valida contra la CA"

# 4) Permisos mínimos
chmod 755 "$CERT_DIR"; chmod 700 "$CA_DIR"
chmod 644 "$CERT_DIR/ca.pem" "$CERT_DIR/server-cert.pem"
# La carpeta hereda el grupo "sarais" (setgid): los certificados públicos quedan de root
chown root:root "$CERT_DIR/ca.pem" "$CERT_DIR/server-cert.pem"
chmod 600 "$CERT_DIR/server-key.pem" "$CA_DIR/ca-key.pem"
chown "$MYSQL_UID:$MYSQL_UID" "$CERT_DIR/server-key.pem"
chown -R root:root "$CA_DIR"

log INFO "Certificados de MySQL creados (SAN: $SAN)"
openssl x509 -in "$CERT_DIR/server-cert.pem" -noout -subject -enddate
ls -ln "$CERT_DIR"
log INFO "Reinicia MySQL y la app:  docker compose up -d --force-recreate mysql_db app"
