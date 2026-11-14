# MySQL 8.4 LTS con cifrado de tablespaces (componente keyring_file)
FROM mysql:8.4

# 1) Manifiesto global: le dice a mysqld que cargue el keyring al arrancar.
#    Debe estar junto al binario mysqld (/usr/sbin en esta imagen).
COPY keyring/mysqld.my /usr/sbin/mysqld.my

# 2) Configuración del componente: va en el plugin_dir de la imagen.
#    Si cambia la imagen, verifica con: SELECT @@plugin_dir;
COPY keyring/component_keyring_file.cnf /usr/lib64/mysql/plugin/component_keyring_file.cnf

# 3) Configuración del servidor (cifrado por defecto, utf8mb4, etc.)
COPY conf.d/sarais.cnf /etc/mysql/conf.d/sarais.cnf

# 4) Script que crea los usuarios de mínimo privilegio (se ejecuta solo la 1.ª vez)
COPY init/05_users.sh /docker-entrypoint-initdb.d/05_users.sh

# Carpeta del llavero: separada de los datos y solo para el usuario mysql
RUN mkdir -p /var/lib/mysql-keyring \
 && chown -R mysql:mysql /var/lib/mysql-keyring /var/lib/mysql \
 && chmod 750 /var/lib/mysql-keyring \
 && chmod 644 /usr/sbin/mysqld.my /usr/lib64/mysql/plugin/component_keyring_file.cnf /etc/mysql/conf.d/sarais.cnf \
 && chmod 644 /docker-entrypoint-initdb.d/05_users.sh

# Usuario no root
USER mysql

# Healthcheck por TCP: falla mientras corre el servidor temporal de inicialización
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD mysqladmin ping -h 127.0.0.1 --silent || exit 1
