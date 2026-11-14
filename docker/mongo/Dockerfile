# MongoDB 7 (los scripts de init y CRUD se montan desde db/mongo como volúmenes)
FROM mongo:7.0

# La imagen ya trae el usuario mongodb y /data/db le pertenece
RUN mkdir -p /scripts && chown mongodb:mongodb /scripts

# Usuario no root
USER mongodb

# "ping" no necesita autenticación
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
  CMD mongosh --quiet --eval "quit(db.adminCommand('ping').ok ? 0 : 1)" || exit 1
