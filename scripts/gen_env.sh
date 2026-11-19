#!/usr/bin/env bash
# gen_env.sh - Crea y valida el .env de la VM SIN editarlo a mano (evita \r de Windows y
# caracteres raros de nano). Todos los secretos son NUEVOS y aleatorios.
# Uso (como sarais_ops, desde la raíz del repo):
#   ./scripts/gen_env.sh                      crea .env (se niega si ya existe)
#   ./scripts/gen_env.sh --set CLAVE=VALOR    cambia una variable (repetible) y valida
#   ./scripts/gen_env.sh --check              solo valida
# FORCE=1 permite reemplazar un .env existente. ¡Cuidado! Con volúmenes ya creados,
# las contraseñas nuevas NO coinciden con las de las bases (habría que reconstruirlas).
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
init_logging
require_cmd openssl awk grep
cd "$PROJECT_DIR"
ENV_FILE=".env"
umask 077

# --- Validación: devuelve error si algo está mal ---
check_env() {
  local errors=0 line
  [[ -f "$ENV_FILE" ]] || die "No existe $ENV_FILE"
  if grep -q $'\r' "$ENV_FILE"; then
    echo "  [FAIL] tiene finales de línea de Windows (\\r). Arreglo: sed -i 's/\\r\$//' .env"; errors=$((errors+1)); fi
  # Fuera de los comentarios solo se permiten caracteres ASCII visibles (sin tildes, tabs ni \r)
  local bad; bad="$(LC_ALL=C awk '!/^#/ && /[^ -~]/ {printf "%d ", NR}' "$ENV_FILE")"
  if [[ -n "$bad" ]]; then
    echo "  [FAIL] caracteres no ASCII o invisibles en las líneas: $bad"; errors=$((errors+1)); fi
  # Cada línea: vacía, comentario o CLAVE=valor sin espacios
  while IFS= read -r line; do
    echo "  [FAIL] línea con formato inválido: ${line%%=*}=..."; errors=$((errors+1))
  done < <(grep -vE '^(#.*|[A-Z_][A-Z0-9_]*=[^ ]*|)$' "$ENV_FILE" || true)
  if grep -q 'cambia_esto' "$ENV_FILE"; then echo "  [FAIL] quedan valores 'cambia_esto'"; errors=$((errors+1)); fi
  grep -qx 'COMPOSE_FILE=docker-compose.yaml' "$ENV_FILE" \
    || { echo "  [FAIL] falta COMPOSE_FILE=docker-compose.yaml (la VM usaría el override)"; errors=$((errors+1)); }
  # Contraseñas: solo letras y números (van dentro de SQL y de la URI de Mongo)
  while IFS='=' read -r k v; do
    [[ "$v" =~ ^[A-Za-z0-9]{16,}$ ]] || { echo "  [FAIL] $k debe ser alfanumérica de 16+ caracteres"; errors=$((errors+1)); }
  done < <(grep -E '^[A-Z_]*PASSWORD=' "$ENV_FILE")
  local sk; sk="$(grep -E '^APP_SECRET_KEY=' "$ENV_FILE" | cut -d= -f2-)"
  (( ${#sk} >= 32 )) || { echo "  [FAIL] APP_SECRET_KEY tiene menos de 32 caracteres"; errors=$((errors+1)); }
  local mode; mode="$(stat -c '%a' "$ENV_FILE")"
  [[ "$mode" == "600" ]] || { echo "  [FAIL] permisos $mode (deben ser 600)"; errors=$((errors+1)); }
  # Docker Compose debe leerlo y publicar SOLO el 443
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    local pub
    pub="$(docker compose config 2>&1 | grep -E 'published:' | tr -d ' "' | sort -u | tr '\n' ' ')" \
      || { echo "  [FAIL] docker compose config falló"; errors=$((errors+1)); }
    [[ "$pub" == "published:443 " ]] && echo "  [OK]   puertos publicados: solo 443" \
      || { echo "  [FAIL] puertos publicados: '$pub' (debe ser solo 443)"; errors=$((errors+1)); }
  fi
  if (( errors == 0 )); then log INFO ".env válido (permisos 600, sin \\r, sin valores por defecto)"
  else die ".env tiene $errors problema(s)"; fi
}

# --- Cambiar una variable sin editor ---
set_var() {
  local kv="$1" k v
  k="${kv%%=*}"; v="${kv#*=}"
  [[ "$k" =~ ^[A-Z_][A-Z0-9_]*$ ]] || die "Nombre inválido: $k"
  [[ "$v" =~ ^[A-Za-z0-9@._:/+=-]*$ ]] || die "Valor con caracteres no permitidos para $k"
  local tmp; tmp="$(mktemp .env.tmp.XXXXXX)"
  awk -v k="$k" -v v="$v" -F= '
    $1==k {print k"="v; done=1; next} {print}
    END {if(!done) print k"="v}' "$ENV_FILE" > "$tmp"
  chmod 600 "$tmp"; mv "$tmp" "$ENV_FILE"
  log INFO "Variable actualizada: $k"
}

case "${1:-}" in
  --check) check_env; exit 0 ;;
  --set)
    [[ -f "$ENV_FILE" ]] || die "Primero crea el .env: ./scripts/gen_env.sh"
    while [[ $# -gt 0 ]]; do
      [[ "$1" == "--set" && -n "${2:-}" ]] || die "Uso: --set CLAVE=VALOR [--set CLAVE=VALOR ...]"
      set_var "$2"; shift 2
    done
    check_env; exit 0 ;;
  "") ;;
  *) die "Opción desconocida: $1" ;;
esac

# --- Crear .env nuevo ---
[[ -f .env.example ]] || die "No existe .env.example (¿estás en la raíz del repo?)"
if [[ -f "$ENV_FILE" && "${FORCE:-0}" != "1" ]]; then
  die "Ya existe .env. No se sobrescribe (los volúmenes usan esas contraseñas). Valida con --check"
fi

pw()  { openssl rand -hex 24; }                                      # 48 caracteres hex
b64() { openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n'; }      # 32 bytes, base64 urlsafe

tmp="$(mktemp .env.tmp.XXXXXX)"
# Se lee .env.example quitando posibles \r, y se reemplaza cada valor que lo necesita
sed 's/\r$//' .env.example | while IFS= read -r line; do
  case "$line" in
    "# COMPOSE_FILE=docker-compose.yaml") echo "COMPOSE_FILE=docker-compose.yaml" ;;
    *PASSWORD=cambia_esto)  echo "${line%%=*}=$(pw)" ;;
    APP_SECRET_KEY=*)       echo "APP_SECRET_KEY=$(openssl rand -hex 32)" ;;
    APP_TOTP_ENC_KEY=*)     echo "APP_TOTP_ENC_KEY=$(b64)" ;;
    *)                      echo "$line" ;;
  esac
done > "$tmp"
chmod 600 "$tmp"; mv "$tmp" "$ENV_FILE"
log INFO ".env creado con secretos nuevos (no se muestran en pantalla)"
check_env
cat <<'EOF'

Siguiente: cuando importes las llaves GPG, fija sus HUELLAS (no los correos):
  ./scripts/gen_env.sh --set BACKUP_GPG_RECIPIENT=<HUELLA_BACKUP> --set DOCS_GPG_RECIPIENT=<HUELLA_DOCS>
EOF
