#!/usr/bin/env bash
# Funciones compartidas por todos los scripts de SARAIS.
# Se usa con:  source "$(dirname "$0")/lib/common.sh"

# Carpeta raíz del repositorio (scripts/..)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_NAME="$(basename "$0" .sh)"
umask 027   # archivos nuevos: sin permisos para "otros"

# Lee .env sin ejecutarlo (más seguro que "source").
# Una variable que ya exista en el entorno tiene prioridad (útil para pruebas).
load_env() {
  local env_file="${ENV_FILE:-$PROJECT_DIR/.env}"
  [[ -f "$env_file" ]] || { echo "ERROR: no existe $env_file" >&2; exit 1; }
  local key value
  while IFS='=' read -r key value || [[ -n "$key" ]]; do
    [[ "$key" =~ ^[[:space:]]*# || -z "${key// }" ]] && continue
    key="${key// /}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    value="${value%$'\r'}"                       # por si .env tiene finales de Windows
    value="${value#\"}"; value="${value%\"}"     # quita comillas opcionales
    [[ -z "${!key+x}" ]] && export "$key=$value"
  done < "$env_file"
}

# Prepara la carpeta de logs (si no se puede escribir, usa ./logs del repo)
init_logging() {
  LOG_DIR="${LOG_DIR:-/var/log/sarais}"
  if ! mkdir -p "$LOG_DIR" 2>/dev/null || [[ ! -w "$LOG_DIR" ]]; then
    LOG_DIR="$PROJECT_DIR/logs"
    mkdir -p "$LOG_DIR"
  fi
  LOG_FILE="$LOG_DIR/${SCRIPT_NAME}.log"
}

# log NIVEL mensaje  ->  pantalla + archivo
log() {
  local level="$1"; shift
  local line
  line="$(date '+%Y-%m-%d %H:%M:%S') [$level] [$SCRIPT_NAME] $*"
  echo "$line"
  [[ -n "${LOG_FILE:-}" ]] && echo "$line" >> "$LOG_FILE"
}

die() { log ERROR "$*"; exit 1; }

# Verifica que existan los comandos necesarios
require_cmd() {
  local c
  for c in "$@"; do
    command -v "$c" >/dev/null 2>&1 || die "Falta el comando: $c"
  done
}

# Evita que el mismo script corra dos veces a la vez (p. ej. cron + manual)
acquire_lock() {
  local lock_file="/tmp/sarais_${SCRIPT_NAME}.lock"
  exec 9>"$lock_file"
  flock -n 9 || die "Ya hay otra ejecución de $SCRIPT_NAME en curso"
}

# ¿El contenedor está corriendo?
container_running() {
  [[ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" == "true" ]]
}

# Nombres de contenedores (deben coincidir con docker-compose.yaml)
MYSQL_CONTAINER="${MYSQL_CONTAINER:-mysql_db}"
MONGO_CONTAINER="${MONGO_CONTAINER:-mongo_db}"
APP_CONTAINER="${APP_CONTAINER:-sarais_app}"
NGINX_CONTAINER="${NGINX_CONTAINER:-sarais_nginx}"
