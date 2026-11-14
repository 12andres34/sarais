#!/usr/bin/env bash
# restore.sh - Restaura un backup creado por backup.sh.
# Necesita la LLAVE PRIVADA GPG (no vive en la VM; impórtala solo para restaurar).
# Uso:
#   ./scripts/restore.sh [--yes] [--only mysql|mongo|docs] /ruta/sarais_AAAAMMDD_HHMMSS.tar.gz.gpg
# Prueba en entorno limpio:
#   docker compose down -v && docker compose up -d   (esperar "healthy")
#   ./scripts/restore.sh --yes <archivo>
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
load_env
init_logging
acquire_lock
require_cmd docker gpg tar sha256sum

ASSUME_YES=false
ONLY="all"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) ASSUME_YES=true; shift ;;
    --only) ONLY="${2:?--only necesita mysql|mongo|docs}"; shift 2 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) FILE="$1"; shift ;;
  esac
done
[[ -n "${FILE:-}" && -f "$FILE" ]] || die "Indica un archivo de backup válido (.tar.gz.gpg)"
[[ "$ONLY" =~ ^(all|mysql|mongo|docs)$ ]] || die "--only debe ser mysql, mongo o docs"

log INFO "Restauración solicitada: $FILE (partes: $ONLY)"

# --- 1) Integridad: el checksum debe coincidir ---
if [[ -f "$FILE.sha256" ]]; then
  (cd "$(dirname "$FILE")" && sha256sum -c --quiet "$(basename "$FILE").sha256") \
    || die "El checksum NO coincide: el archivo está dañado o fue modificado"
  log INFO "Checksum SHA-256 correcto"
else
  log WARN "No hay archivo .sha256: no se puede verificar la integridad"
fi

# --- 2) Descifrar y extraer en una carpeta temporal privada ---
WORK="$(mktemp -d /tmp/sarais_restore.XXXXXX)"
chmod 700 "$WORK"
trap 'rm -rf "$WORK"' EXIT
gpg --batch --decrypt "$FILE" 2>>"$LOG_FILE" | tar -xzf - -C "$WORK" \
  || die "No se pudo descifrar (¿falta la llave privada GPG?)"
log INFO "Backup descifrado. Manifiesto:"
sed 's/^/    /' "$WORK/MANIFEST.txt"

# Verifica cada archivo interno contra el manifiesto
(cd "$WORK" && grep -E '^[0-9a-f]{64}  ' MANIFEST.txt | sha256sum -c --quiet) \
  || die "Los archivos internos no coinciden con el manifiesto"

# --- 3) Confirmación (sobrescribe datos actuales) ---
if ! $ASSUME_YES; then
  read -r -p "Esto REEMPLAZA los datos actuales ($ONLY). Escribe 'si' para continuar: " ans
  [[ "$ans" == "si" ]] || die "Cancelado por el usuario"
fi

# --- 4) MySQL (usa root, leído dentro del contenedor) ---
if [[ "$ONLY" == all || "$ONLY" == mysql ]]; then
  container_running "$MYSQL_CONTAINER" || die "$MYSQL_CONTAINER no está corriendo"
  log INFO "Restaurando MySQL..."
  docker exec -i "$MYSQL_CONTAINER" sh -c \
    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot' < "$WORK/mysql_dump.sql"
  tables="$(docker exec "$MYSQL_CONTAINER" sh -c \
    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -e \
     "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=\"$MYSQL_DATABASE\""')"
  log INFO "MySQL restaurado: $tables tablas/vistas en la base"
fi

# --- 5) MongoDB (--drop reemplaza las colecciones; conserva validadores e índices) ---
if [[ "$ONLY" == all || "$ONLY" == mongo ]]; then
  container_running "$MONGO_CONTAINER" || die "$MONGO_CONTAINER no está corriendo"
  log INFO "Restaurando MongoDB..."
  docker exec -i "$MONGO_CONTAINER" sh -c \
    'exec mongorestore --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" \
       --authenticationDatabase admin --archive --gzip --drop \
       --nsInclude "$MONGO_INITDB_DATABASE.*"' < "$WORK/mongo_dump.archive.gz"
  count="$(docker exec "$MONGO_CONTAINER" sh -c \
    'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" \
       --authenticationDatabase admin "$MONGO_INITDB_DATABASE" \
       --eval "db.audit_logs.countDocuments()"')"
  log INFO "MongoDB restaurado: audit_logs tiene $count documentos"
fi

# --- 6) Documentos cifrados ---
if [[ "$ONLY" == all || "$ONLY" == docs ]]; then
  if [[ -f "$WORK/documents.tar" ]]; then
    container_running "$APP_CONTAINER" || die "$APP_CONTAINER no está corriendo"
    docker exec -i "$APP_CONTAINER" tar -C /srv/data -xf - < "$WORK/documents.tar"
    log INFO "Documentos restaurados"
  else
    log WARN "El backup no incluye documentos"
  fi
fi

log INFO "Restauración terminada. Registra este evento en la bitácora de auditoría."
