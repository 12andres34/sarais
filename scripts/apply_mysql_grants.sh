#!/usr/bin/env bash
# apply_mysql_grants.sh - Deja al usuario de la app con el MÍNIMO privilegio en una base YA creada.
# (05_users.sh solo corre la primera vez; este script corrige volúmenes existentes.)
# Idempotente: se puede repetir.  Uso: ./scripts/apply_mysql_grants.sh
#
# La app necesita SELECT, INSERT, UPDATE (+ SELECT ... FOR UPDATE, que MySQL permite con
# SELECT + UPDATE) y leer la vista v_report_card. No usa DELETE ni DDL.
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
init_logging
require_cmd docker
C="${MYSQL_CONTAINER:-mysql_db}"

# Las comillas simples hacen que las variables se lean DENTRO del contenedor:
# las contraseñas nunca pasan por el host. \` es una comilla invertida de MySQL.
docker exec "$C" sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -t -e "
  REVOKE ALL PRIVILEGES, GRANT OPTION FROM \`$MYSQL_APP_USER\`@\`%\`;
  GRANT SELECT, INSERT, UPDATE ON \`$MYSQL_DATABASE\`.* TO \`$MYSQL_APP_USER\`@\`%\`;
  ALTER USER \`$MYSQL_APP_USER\`@\`%\` REQUIRE SSL;
  SHOW GRANTS FOR \`$MYSQL_APP_USER\`@\`%\`;
  SELECT user, host, ssl_type FROM mysql.user WHERE user = \"$MYSQL_APP_USER\";"'

log INFO "Usuario de la app: solo SELECT, INSERT, UPDATE y TLS obligatorio (ssl_type = ANY)"
