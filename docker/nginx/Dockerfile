# Nginx como proxy inverso con TLS.
# Imagen oficial "unprivileged": corre como usuario nginx (UID 101), no root.
FROM nginxinc/nginx-unprivileged:1.27-alpine

# Reemplazamos la configuración por defecto
COPY --chown=101:101 nginx.conf /etc/nginx/nginx.conf
COPY --chown=101:101 proxy_params_sarais /etc/nginx/proxy_params_sarais
# Quitamos el sitio por defecto (escucha en 8080 en todas las interfaces)
USER root
RUN rm -f /etc/nginx/conf.d/default.conf

# Usuario no root (ya viene en la imagen, lo dejamos explícito)
USER 101

# 8080 = solo healthcheck interno, 8443 = HTTPS
EXPOSE 8443

# Healthcheck sin TLS, dentro del contenedor (wget viene en Alpine/busybox)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/nginx-health || exit 1
