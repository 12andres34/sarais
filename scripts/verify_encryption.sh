#!/usr/bin/env bash
# Verifica cifrado en reposo y en tránsito de MySQL. Solo lee, no cambia nada.
# Uso: ./scripts/verify_encryption.sh      (contenedor mysql_db en marcha)
set -uo pipefail

C="${MYSQL_CONTAINER:-mysql_db}"
pass=0; fail=0; warn=0
ok()   { echo "  [PASS] $*"; pass=$((pass+1)); }
bad()  { echo "  [FAIL] $*"; fail=$((fail+1)); }
note() { echo "  [WARN] $*"; warn=$((warn+1)); }

# Ejecuta SQL como root por socket. MYSQL_PWD evita poner la contraseña en la línea de comandos.
q() { docker exec "$C" sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B -e "$1"' _ "$1" 2>/dev/null; }
DB="$(docker exec "$C" printenv MYSQL_DATABASE)"

echo "== 1. Keyring =="
status="$(q "SELECT STATUS_VALUE FROM performance_schema.keyring_component_status WHERE STATUS_KEY='Component_status'")"
[[ "$status" == "Active" ]] && ok "keyring Active" || bad "keyring no está Active ($status)"

kfile="$(q "SELECT STATUS_VALUE FROM performance_schema.keyring_component_status WHERE STATUS_KEY='Data_file'")"
echo "  archivo del keyring: ${kfile:-?}"
if [[ -z "$kfile" ]]; then bad "no se pudo leer la ruta del keyring"
elif [[ "$kfile" == /var/lib/mysql/* ]]; then bad "keyring DENTRO del volumen de datos (debe estar fuera)"
else ok "keyring fuera de /var/lib/mysql"; fi

kdir="$(dirname "${kfile:-/x}")"
mounts="$(docker inspect "$C" --format '{{range .Mounts}}{{.Destination}} {{end}}')"
if grep -qw "$kdir" <<<"$mounts"; then ok "directorio $kdir está montado (sobrevive a recrear el contenedor)"
else bad "directorio $kdir NO está montado: al recrear el contenedor se PIERDE la llave"; fi

perm="$(docker exec "$C" stat -c '%a %U' "$kfile" 2>/dev/null)"
[[ "$perm" == "600 mysql" || "$perm" == "400 mysql" ]] && ok "permisos keyring: $perm" || note "permisos keyring: '$perm' (esperado 600 mysql)"
dperm="$(docker exec "$C" stat -c '%a' "$kdir" 2>/dev/null)"
[[ "$dperm" == "700" || "$dperm" == "750" ]] && ok "permisos dir keyring: $dperm" || note "dir keyring: '$dperm' (esperado 700)"

echo "== 2. Variables de cifrado =="
for v in default_table_encryption require_secure_transport innodb_redo_log_encrypt innodb_undo_log_encrypt binlog_encryption; do
  val="$(q "SELECT @@$v")"
  [[ "$val" == "1" || "$val" == "ON" ]] && ok "$v = ON" || bad "$v = $val"
done

echo "== 3. Tablas y esquema =="
total="$(q "SELECT COUNT(*) FROM information_schema.INNODB_TABLESPACES WHERE NAME LIKE '${DB}/%'")"
enc="$(q "SELECT COUNT(*) FROM information_schema.INNODB_TABLESPACES WHERE NAME LIKE '${DB}/%' AND ENCRYPTION='Y'")"
[[ -n "$total" && "$total" == "$enc" && "$total" -gt 0 ]] && ok "$enc/$total tablespaces cifrados" || bad "$enc/$total tablespaces cifrados"
sch="$(q "SELECT DEFAULT_ENCRYPTION FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='${DB}'")"
[[ "$sch" == "YES" ]] && ok "esquema $DB DEFAULT ENCRYPTION=Y" || note "esquema $DB DEFAULT ENCRYPTION=$sch (ver docs/security_design.md §2.2)"

echo "== 4. TLS =="
# --get-server-public-key: sin él, el cliente aborta antes (2061, caching_sha2_password)
# y nunca llega a ver la respuesta del servidor. Con él, el servidor responde 3159.
out="$(docker exec "$C" sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -h127.0.0.1 --ssl-mode=DISABLED --get-server-public-key -e "SELECT 1"' 2>&1)"
if grep -q "3159" <<<"$out"; then ok "TCP sin TLS rechazado por el servidor (error 3159)"
elif grep -q "2061" <<<"$out"; then ok "TCP sin TLS rechazado (error 2061: la autenticación exige conexión segura)"
elif grep -qi "denied" <<<"$out"; then note "root no entra por TCP (bien); prueba 3159 con el usuario de la app (docs/security_tests.md)"
else bad "TCP sin TLS NO fue rechazado: $out"; fi

ver="$(docker exec "$C" sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -h127.0.0.1 --ssl-mode=VERIFY_IDENTITY --ssl-ca=/etc/mysql/certs/ca.pem -N -e "SHOW SESSION STATUS LIKE \"Ssl_version\""' 2>&1)"
grep -q "TLSv1.[23]" <<<"$ver" && ok "TLS verificado con la CA: $(awk '{print $2}' <<<"$ver")" || note "VERIFY_IDENTITY: $ver"

echo "  conexiones activas (usuario / tipo):"
q "SELECT PROCESSLIST_USER, CONNECTION_TYPE, COUNT(*) FROM performance_schema.threads WHERE PROCESSLIST_USER IS NOT NULL GROUP BY 1,2" | sed 's/^/    /'
app_plain="$(q "SELECT COUNT(*) FROM performance_schema.threads WHERE PROCESSLIST_USER NOT IN ('root','event_scheduler') AND CONNECTION_TYPE='TCP/IP'")"
[[ "$app_plain" == "0" ]] && ok "ninguna conexión de la app sin TLS" || bad "$app_plain conexiones TCP sin TLS"

echo "== 5. Healthcheck =="
h="$(docker inspect "$C" --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}')"
[[ "$h" == "healthy" ]] && ok "healthcheck: healthy" || note "healthcheck: ${h:-sin healthcheck}"

echo; echo "Resultado: $pass PASS, $fail FAIL, $warn WARN"
[[ $fail -eq 0 ]]