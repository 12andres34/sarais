#!/bin/bash
# Crea las cuentas de mínimo privilegio. El entrypoint oficial "sourcea" este
# archivo (no es ejecutable), por eso podemos usar docker_process_sql.
# Usa contraseñas alfanuméricas (sin comillas) en .env.

: "${MYSQL_DATABASE:?falta MYSQL_DATABASE}"
: "${MYSQL_APP_USER:?falta MYSQL_APP_USER}"
: "${MYSQL_APP_PASSWORD:?falta MYSQL_APP_PASSWORD}"
: "${MYSQL_BACKUP_USER:?falta MYSQL_BACKUP_USER}"
: "${MYSQL_BACKUP_PASSWORD:?falta MYSQL_BACKUP_PASSWORD}"

echo "[init] creando usuarios ${MYSQL_APP_USER} y ${MYSQL_BACKUP_USER}"

docker_process_sql --database=mysql <<-EOSQL
  -- App: SELECT/INSERT/UPDATE (SELECT ... FOR UPDATE necesita SELECT + UPDATE).
  -- Sin DELETE (la app desactiva, no borra), sin DDL y solo con TLS.
  CREATE USER IF NOT EXISTS '${MYSQL_APP_USER}'@'%' IDENTIFIED BY '${MYSQL_APP_PASSWORD}' REQUIRE SSL;
  GRANT SELECT, INSERT, UPDATE ON \`${MYSQL_DATABASE}\`.* TO '${MYSQL_APP_USER}'@'%';

  -- Backups: solo lectura + lo mínimo que necesita mysqldump
  CREATE USER IF NOT EXISTS '${MYSQL_BACKUP_USER}'@'localhost' IDENTIFIED BY '${MYSQL_BACKUP_PASSWORD}';
  GRANT SELECT, SHOW VIEW, TRIGGER, EVENT, LOCK TABLES ON \`${MYSQL_DATABASE}\`.* TO '${MYSQL_BACKUP_USER}'@'localhost';
  GRANT SHOW_ROUTINE ON *.* TO '${MYSQL_BACKUP_USER}'@'localhost';  -- para --routines

  FLUSH PRIVILEGES;
EOSQL
