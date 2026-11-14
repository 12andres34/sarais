#!/usr/bin/env bash
# cleanup.sh - Mantenimiento: rota/comprime logs, borra métricas viejas,
# restos temporales de backups e imágenes Docker sin uso. NUNCA borra volúmenes.
# Uso:   ./scripts/cleanup.sh [--dry-run]
# Cron:  30 3 * * 0 /opt/sarais/scripts/cleanup.sh >> /var/log/sarais/cron.log 2>&1
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
load_env
init_logging
acquire_lock
require_cmd find gzip df

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

LOG_RETENTION="${LOG_RETENTION_DAYS:-30}"
METRICS_RETENTION="${METRICS_RETENTION_DAYS:-90}"
METRICS_DIR="${METRICS_DIR:-$LOG_DIR/metrics}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/sarais}"
MAX_LOG_BYTES=$((5 * 1024 * 1024))   # rota un log al pasar 5 MB

# Ejecuta o solo muestra (modo --dry-run)
run() { if $DRY_RUN; then log INFO "[dry-run] $*"; else "$@"; fi; }

# Borra los archivos que encuentre find, mostrando cuántos
purge() {
  local desc="$1"; shift
  local files
  mapfile -t files < <(find "$@" 2>/dev/null)
  log INFO "$desc: ${#files[@]} archivo(s)"
  local f
  for f in "${files[@]}"; do run rm -f -- "$f"; done
}

disk_before="$(df -P -k / | awk 'NR==2{print $4}')"
log INFO "Inicio de limpieza (dry-run=$DRY_RUN)"

# 1) Rotar logs grandes: archivo.log -> archivo.log.AAAAMMDD_HHMMSS.gz
for f in "$LOG_DIR"/*.log; do
  [[ -f "$f" ]] || continue
  [[ "$f" == "$LOG_FILE" ]] && continue      # no rotar el log que estamos escribiendo
  if (( $(stat -c %s "$f") > MAX_LOG_BYTES )); then
    rotated="$f.$(date '+%Y%m%d_%H%M%S')"
    run mv -- "$f" "$rotated"
    run gzip -- "$rotated"
    log INFO "Log rotado: $(basename "$f")"
  fi
done

# 2) Borrar logs rotados viejos
purge "Logs comprimidos con más de $LOG_RETENTION días" \
  "$LOG_DIR" -maxdepth 1 -name '*.log.*.gz' -mtime +"$LOG_RETENTION"

# 3) Métricas: comprimir CSV de más de 35 días y borrar los de más de N días
mapfile -t old_csv < <(find "$METRICS_DIR" -maxdepth 1 -name 'metrics_*.csv' -mtime +35 2>/dev/null)
for f in "${old_csv[@]}"; do run gzip -- "$f"; done
log INFO "CSV de métricas comprimidos: ${#old_csv[@]}"
purge "Métricas con más de $METRICS_RETENTION días" \
  "$METRICS_DIR" -maxdepth 1 -name 'metrics_*.csv.gz' -mtime +"$METRICS_RETENTION"

# 4) Carpetas temporales de backups interrumpidos
if [[ -d "$BACKUP_DIR" ]]; then
  mapfile -t stale < <(find "$BACKUP_DIR" -maxdepth 1 -type d -name '.tmp.*' -mmin +120 2>/dev/null)
  for d in "${stale[@]}"; do run rm -rf -- "$d"; done
  log INFO "Temporales de backup borrados: ${#stale[@]}"
fi

# 5) Docker: imágenes "colgadas" y caché de build de más de 7 días (no toca volúmenes)
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  run docker image prune -f
  run docker builder prune -f --filter until=168h
else
  log WARN "Docker no disponible: se omite la limpieza de imágenes"
fi

disk_after="$(df -P -k / | awk 'NR==2{print $4}')"
log INFO "Limpieza terminada. Espacio liberado: $(( (disk_after - disk_before) / 1024 )) MB"
