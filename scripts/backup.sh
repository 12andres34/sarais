#!/usr/bin/env bash
# backup.sh - Copia de seguridad cifrada de SARAIS.
#   1) mysqldump (usuario de solo lectura)   2) mongodump   3) documentos cifrados
#   4) todo en un .tar.gz cifrado con GPG (llave pública) + checksum SHA-256
#   5) rotación (borra los más viejos)       6) copia externa opcional
# Uso:   ./scripts/backup.sh
# Cron:  0 2 * * * /opt/sarais/scripts/backup.sh >> /var/log/sarais/cron.log 2>&1
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
load_env
init_logging
acquire_lock
require_cmd docker gpg tar gzip sha256sum find

BACKUP_DIR="${BACKUP_DIR:-/var/backups/sarais}"
RETENTION="${BACKUP_RETENTION_DAYS:-7}"
RECIPIENT="${BACKUP_GPG_RECIPIENT:?Falta BACKUP_GPG_RECIPIENT en .env}"
TS="$(date '+%Y%m%d_%H%M%S')"
FINAL="$BACKUP_DIR/sarais_${TS}.tar.gz.gpg"

log INFO "Inicio del backup -> $FINAL"

# --- Comprobaciones previas ---
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
gpg --batch --list-keys "$RECIPIENT" >/dev/null 2>&1 \
  || die "No está la llave pública GPG '$RECIPIENT'. Impórtala con: gpg --import backup_pub.asc"
container_running "$MYSQL_CONTAINER" || die "El contenedor $MYSQL_CONTAINER no está corriendo"
container_running "$MONGO_CONTAINER" || die "El contenedor $MONGO_CONTAINER no está corriendo"

# Carpeta temporal privada; se borra siempre al salir (aunque haya error)
WORK="$(mktemp -d "$BACKUP_DIR/.tmp.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# --- 1) MySQL ---
# Las credenciales se leen DENTRO del contenedor (no aparecen en el host).
log INFO "mysqldump..."
docker exec "$MYSQL_CONTAINER" sh -c \
  'MYSQL_PWD="$MYSQL_BACKUP_PASSWORD" exec mysqldump -u"$MYSQL_BACKUP_USER" \
     --single-transaction --routines --triggers --events \
     --no-tablespaces --set-gtid-purged=OFF \
     --databases "$MYSQL_DATABASE"' > "$WORK/mysql_dump.sql"
# Un dump completo termina con esta línea
tail -n 1 "$WORK/mysql_dump.sql" | grep -q "Dump completed" \
  || die "El dump de MySQL está incompleto"
log INFO "MySQL OK ($(du -h "$WORK/mysql_dump.sql" | cut -f1))"

# --- 2) MongoDB ---
log INFO "mongodump..."
docker exec "$MONGO_CONTAINER" sh -c \
  'exec mongodump --quiet -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" \
     --authenticationDatabase admin --db "$MONGO_INITDB_DATABASE" --archive --gzip' \
  > "$WORK/mongo_dump.archive.gz"
[[ -s "$WORK/mongo_dump.archive.gz" ]] || die "El dump de MongoDB está vacío"
log INFO "MongoDB OK ($(du -h "$WORK/mongo_dump.archive.gz" | cut -f1))"

# --- 3) Documentos (ya están cifrados con GPG por la app) ---
if container_running "$APP_CONTAINER"; then
  docker exec "$APP_CONTAINER" tar -C /srv/data -cf - documents > "$WORK/documents.tar"
  log INFO "Documentos OK ($(du -h "$WORK/documents.tar" | cut -f1))"
else
  log WARN "La app no está corriendo: se omiten los documentos"
fi

# --- Manifiesto (qué contiene el backup) ---
# Los hashes se calculan ANTES de crear MANIFEST.txt (para no incluirlo a sí mismo)
hashes="$(cd "$WORK" && sha256sum -- *)"
{
  echo "created_at=$(date -Iseconds)"
  echo "host=$(hostname)"
  echo "git_commit=$(git -C "$PROJECT_DIR" rev-parse --short HEAD 2>/dev/null || echo n/a)"
  echo "$hashes"
} > "$WORK/MANIFEST.txt"

# --- 4) Empaquetar + cifrar (nunca se escribe el .tar sin cifrar en disco) ---
log INFO "Comprimiendo y cifrando para $RECIPIENT..."
tar -C "$WORK" -czf - . \
  | gpg --batch --yes --trust-model always --encrypt --recipient "$RECIPIENT" --output "$FINAL"
chmod 600 "$FINAL"
(cd "$BACKUP_DIR" && sha256sum "$(basename "$FINAL")" > "$(basename "$FINAL").sha256")
log INFO "Backup cifrado: $FINAL ($(du -h "$FINAL" | cut -f1))"

# --- 5) Rotación ---
rotate() {
  local dir="$1" n
  n="$(find "$dir" -maxdepth 1 -name 'sarais_*.tar.gz.gpg*' -mtime +"$RETENTION" | wc -l)"
  find "$dir" -maxdepth 1 -name 'sarais_*.tar.gz.gpg*' -mtime +"$RETENTION" -delete
  log INFO "Rotación en $dir: $n archivo(s) con más de $RETENTION días borrados"
}
rotate "$BACKUP_DIR"

# --- 6) Copia externa (opcional) ---
if [[ -n "${BACKUP_EXTERNAL_DIR:-}" ]]; then
  if [[ -d "$BACKUP_EXTERNAL_DIR" && -w "$BACKUP_EXTERNAL_DIR" ]]; then
    cp -p "$FINAL" "$FINAL.sha256" "$BACKUP_EXTERNAL_DIR/"
    log INFO "Copia externa en $BACKUP_EXTERNAL_DIR"
    rotate "$BACKUP_EXTERNAL_DIR"
  else
    log WARN "BACKUP_EXTERNAL_DIR=$BACKUP_EXTERNAL_DIR no existe o no se puede escribir"
  fi
fi
if [[ -n "${BACKUP_REMOTE:-}" ]]; then
  require_cmd rsync ssh
  if rsync -a -e "ssh -o BatchMode=yes -o ConnectTimeout=10" "$FINAL" "$FINAL.sha256" "$BACKUP_REMOTE/"; then
    log INFO "Copia remota en $BACKUP_REMOTE"
  else
    log WARN "Falló la copia remota a $BACKUP_REMOTE (el backup local sí quedó)"
  fi
fi

log INFO "Backup terminado correctamente"
