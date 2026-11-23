#!/usr/bin/env bash
# preflight.sh - Revisión ANTES de "docker compose up" en la VM. Solo lee, no cambia nada.
# Uso:  sudo ./scripts/preflight.sh       (sudo: las carpetas de llaves solo las ve root)
# Evita los fallos ya vividos: ca.pem convertido en carpeta, .env con \r, override activo,
# llaves con dueño o permisos equivocados, llaves GPG sin importar, CPU sin AVX.
set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
cd "$PROJECT_DIR"
[[ $EUID -eq 0 ]] || { echo "Ejecuta con sudo" >&2; exit 1; }

OPS_USER="${OPS_USER:-sarais_ops}"
pass=0; fail=0
ok()  { echo "  [PASS] $*"; pass=$((pass+1)); }
bad() { echo "  [FAIL] $*"; fail=$((fail+1)); }

# perm_is <ruta> <modo> <dueño:grupo numérico> <descripción>
perm_is() {
  local p="$1" m="$2" o="$3" d="$4" got
  [[ -f "$p" ]] || { bad "$d: no existe o no es archivo ($p)"; return; }
  got="$(stat -c '%a %u:%g' "$p")"
  [[ "$got" == "$m $o" ]] && ok "$d ($got)" || bad "$d: tiene '$got', se espera '$m $o'"
}

echo "== 1. Repositorio =="
[[ -f docker-compose.yaml && -d scripts ]] && ok "estás en la raíz del repo ($PROJECT_DIR)" || bad "no es la raíz del repo"
if git -C "$PROJECT_DIR" rev-parse --git-dir >/dev/null 2>&1; then
  [[ -z "$(git -C "$PROJECT_DIR" ls-files .env)" ]] && ok ".env no está versionado" || bad ".env está en Git"
  crlf="$(git -C "$PROJECT_DIR" ls-files -z '*.sh' '*.yaml' '*.sql' '*.cnf' | xargs -0 grep -l $'\r' 2>/dev/null | head -5)"
  [[ -z "$crlf" ]] && ok "scripts y configuración sin \\r" || bad "archivos con \\r: $crlf"
else
  echo "  [--]   git no disponible para root (ver safe.directory en la guía)"
fi

echo "== 2. .env =="
if [[ -f .env ]]; then
  # El grupo da igual (la carpeta tiene setgid): con 600 solo lee el dueño
  got="$(stat -c '%a %U' .env)"
  [[ "$got" == "600 $OPS_USER" ]] && ok ".env $got" || bad ".env tiene '$got', se espera '600 $OPS_USER'"
  if sudo -u "$OPS_USER" ./scripts/gen_env.sh --check >/tmp/preflight_env.txt 2>&1; then ok "gen_env.sh --check sin errores"
  else bad "gen_env.sh --check:"; sed 's/^/         /' /tmp/preflight_env.txt; fi
  rm -f /tmp/preflight_env.txt
else
  bad "no existe .env (crea uno con: ./scripts/gen_env.sh como $OPS_USER)"
fi

echo "== 3. Certificados de MySQL (gen_mysql_certs.sh) =="
if [[ -d docker/mysql/certs/ca.pem ]]; then
  bad "ca.pem es una CARPETA (Docker la creó porque faltaba el archivo). Arreglo: sudo rmdir docker/mysql/certs/ca.pem && sudo ./scripts/gen_mysql_certs.sh"
else
  perm_is docker/mysql/certs/ca.pem          644 "0:0"     "ca.pem (público)"
fi
perm_is docker/mysql/certs/server-cert.pem   644 "0:0"     "server-cert.pem (público)"
perm_is docker/mysql/certs/server-key.pem    600 "999:999" "server-key.pem (solo mysql, UID 999)"
perm_is docker/mysql/ca-private/ca-key.pem   600 "0:0"     "ca-key.pem (solo root, no se monta)"
if [[ -f docker/mysql/certs/ca.pem && -f docker/mysql/certs/server-cert.pem ]]; then
  openssl verify -CAfile docker/mysql/certs/ca.pem docker/mysql/certs/server-cert.pem >/dev/null 2>&1 \
    && ok "server-cert.pem firmado por la CA" || bad "server-cert.pem NO valida contra ca.pem"
fi

echo "== 4. Certificado de Nginx (gen_certs.sh) =="
perm_is docker/nginx/certs/sarais.key 640 "0:101" "sarais.key (root + grupo nginx 101)"
if [[ -f docker/nginx/certs/sarais.crt ]]; then
  san="$(openssl x509 -in docker/nginx/certs/sarais.crt -noout -ext subjectAltName 2>/dev/null | tail -1)"
  [[ "$san" == *"192.168.56.10"* ]] && ok "sarais.crt incluye la IP 192.168.56.10" || bad "sarais.crt no incluye 192.168.56.10 ($san)"
  openssl x509 -in docker/nginx/certs/sarais.crt -noout -checkend 2592000 >/dev/null \
    && ok "sarais.crt vigente por más de 30 días" || bad "sarais.crt vence en menos de 30 días"
else
  bad "no existe docker/nginx/certs/sarais.crt"
fi

echo "== 5. GPG de backups (llavero de $OPS_USER) =="
recipient="$(grep -E '^BACKUP_GPG_RECIPIENT=' .env 2>/dev/null | cut -d= -f2-)"
if [[ -n "$recipient" ]] && sudo -u "$OPS_USER" -H gpg --batch --list-keys "$recipient" >/dev/null 2>&1; then
  ok "llave pública '$recipient' importada"
  sudo -u "$OPS_USER" -H gpg --batch --list-secret-keys 2>/dev/null | grep -q . \
    && bad "$OPS_USER tiene llaves PRIVADAS en la VM (no deben estar aquí)" || ok "sin llaves privadas en la VM"
else
  bad "falta la llave pública de backups '$recipient' en el llavero de $OPS_USER"
fi

echo "== 6. Carpetas del sistema (setup_users.sh) =="
[[ "$(stat -c '%a %U' /var/backups/sarais 2>/dev/null)" == "700 $OPS_USER" ]] && ok "/var/backups/sarais 700 $OPS_USER" || bad "/var/backups/sarais: $(stat -c '%a %U' /var/backups/sarais 2>&1)"
[[ "$(stat -c '%a %U %G' /var/log/sarais 2>/dev/null)" == "2750 $OPS_USER sarais-audit" ]] && ok "/var/log/sarais 2750 $OPS_USER:sarais-audit" || bad "/var/log/sarais: $(stat -c '%a %U %G' /var/log/sarais 2>&1)"

echo "== 7. Docker =="
systemctl is-active --quiet docker && ok "servicio docker activo" || bad "docker no está activo"
docker compose version >/dev/null 2>&1 && ok "$(docker compose version)" || bad "falta el plugin docker compose"
# MongoDB 7 exige AVX. Con Hyper-V encendido en Windows, VirtualBox lo esconde (riesgo R24)
grep -qw avx /proc/cpuinfo && ok "la CPU virtual tiene AVX (MongoDB 7)" \
  || bad "sin AVX: mongo_db no arrancará. En Windows: bcdedit /set hypervisorlaunchtype off + reiniciar"

echo "== 8. GPG de documentos (dentro de sarais_app, volumen app_gnupg) =="
docs_rcp="$(grep -E '^DOCS_GPG_RECIPIENT=' .env 2>/dev/null | cut -d= -f2-)"
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx sarais_app; then
  if [[ -n "$docs_rcp" ]] && docker exec sarais_app gpg --batch --list-keys "$docs_rcp" >/dev/null 2>&1; then
    ok "llave pública de documentos '$docs_rcp' importada en sarais_app"
  else
    bad "falta la llave de documentos en sarais_app: docker exec -i sarais_app gpg --batch --import < ~/keys/docs_pub.asc"
  fi
  docker exec sarais_app gpg --batch --list-secret-keys 2>/dev/null | grep -q . \
    && bad "sarais_app tiene llaves PRIVADAS (solo debe tener la pública)" || ok "sarais_app sin llaves privadas"
else
  echo "  [--]   sarais_app no está corriendo (se revisa después del primer up)"
fi

echo; echo "Resultado: $pass PASS, $fail FAIL"
(( fail == 0 )) && echo "Listo para: docker compose up -d --build (como $OPS_USER)"
(( fail == 0 ))
