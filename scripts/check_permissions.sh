#!/usr/bin/env bash
# check_permissions.sh - Revisa permisos de archivos sensibles. Por defecto solo REPORTA.
# Uso: ./scripts/check_permissions.sh           -> reporte
#      sudo ./scripts/check_permissions.sh --fix -> corrige solo con chmod (.env, backups, scripts)
# No cambia dueños de llaves: eso lo hacen gen_certs.sh y gen_mysql_certs.sh.
set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
load_env
cd "$PROJECT_DIR"
FIX=0; [[ "${1:-}" == "--fix" ]] && FIX=1
issues=0

# check <ruta> <modo_máximo_octal> <descripción>  -> FAIL si tiene algún permiso de más
check() {
  local path="$1" max="$2" desc="$3" mode
  [[ -e "$path" ]] || { echo "  [--]   $path no existe ($desc)"; return 0; }
  mode="$(stat -c '%a' "$path")"
  if (( (8#$mode & ~8#$max) != 0 )); then
    echo "  [FAIL] $path = $mode (máximo $max) - $desc"; issues=$((issues+1))
    [[ $FIX -eq 1 ]] && chmod "$max" "$path" && echo "         -> corregido: chmod $max"
    return 0
  fi
  echo "  [OK]   $path = $mode $(stat -c '%U:%G' "$path") - $desc"
}

echo "== Secretos =="
check .env 600 "contraseñas y llaves"
if git rev-parse --git-dir >/dev/null 2>&1; then
  if [[ -n "$(git ls-files .env)" ]]; then echo "  [FAIL] .env está versionado en Git"; issues=$((issues+1))
  else echo "  [OK]   .env no está en Git"; fi
  if [[ -n "$(git log --all --oneline -- .env 2>/dev/null)" ]]; then
    echo "  [FAIL] .env aparece en el historial de Git: cambia TODAS las contraseñas y llaves"; issues=$((issues+1))
  fi
  for f in docker/nginx/certs/sarais.key docker/mysql/certs/server-key.pem docker/mysql/ca-private/ca-key.pem; do
    [[ -e "$f" ]] && ! git check-ignore -q "$f" && { echo "  [FAIL] $f NO está ignorado por Git"; issues=$((issues+1)); }
  done
fi

echo "== Certificados y llaves (no se corrigen con --fix) =="
FIX_SAVED=$FIX; FIX=0
check docker/nginx/certs/sarais.key 640 "llave TLS Nginx (root:101)"
check docker/mysql/certs/server-key.pem 600 "llave TLS MySQL (UID 999)"
check docker/mysql/ca-private 700 "carpeta de la CA de MySQL"
check docker/mysql/ca-private/ca-key.pem 600 "llave de la CA de MySQL"
check docker/mysql/certs/ca.pem 644 "CA pública de MySQL"
FIX=$FIX_SAVED

echo "== Backups ($BACKUP_DIR) =="
if [[ -d "$BACKUP_DIR" ]]; then
  check "$BACKUP_DIR" 700 "carpeta de backups"
  for f in "$BACKUP_DIR"/*; do
    [[ -f "$f" ]] || continue
    check "$f" 640 "backup"
    [[ "$f" == *.gpg || "$f" == *.sha256 ]] || { echo "  [FAIL] $f no está cifrado (.gpg)"; issues=$((issues+1)); }
  done
else
  echo "  [--]   $BACKUP_DIR no existe todavía"
fi

echo "== Scripts =="
for s in scripts/*.sh scripts/linux/*.sh; do check "$s" 755 "script"; done

echo "== Archivos con escritura para todos =="
ww="$(find . -path ./.git -prune -o -type f -perm -o+w -print 2>/dev/null | head -20)"
if [[ -z "$ww" ]]; then echo "  [OK]   ninguno"; else echo "$ww" | sed 's/^/  [FAIL] /'; issues=$((issues+1)); fi
[[ "$PROJECT_DIR" == /mnt/* ]] && echo "  [WARN] El repo está en /mnt (disco de Windows): chmod no funciona. Muévelo a ~/ en WSL."

echo "== Grupo docker (equivale a root) =="
echo "  miembros: $(getent group docker | cut -d: -f4)"
echo "  (ver riesgo R11 en docs/risk_analysis.md)"

echo; echo "Problemas: $issues"
[[ $issues -eq 0 ]]
