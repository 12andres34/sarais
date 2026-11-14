# db/mongo

```
init/01_init_mongo.js          # colecciones + JSON Schema + índices + rol + usuario app
scripts/document_metadata_crud.js   # CRUD completo
scripts/audit_logs_crud.js          # solo crear y leer
scripts/verify.js                   # pruebas de seguridad (deben dar PASS)
```

## Agregar a docker-compose.yaml (servicio base)

```yaml
  mongo_db:
    image: mongo:7
    container_name: mongo_db
    restart: unless-stopped
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_ROOT_USER}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_ROOT_PASSWORD}
      MONGO_INITDB_DATABASE: ${MONGO_DB}
      MONGO_APP_USER: ${MONGO_APP_USER}
      MONGO_APP_PASSWORD: ${MONGO_APP_PASSWORD}
    volumes:
      - mongo_data:/data/db
      - ./db/mongo/init:/docker-entrypoint-initdb.d:ro
      - ./db/mongo/scripts:/scripts:ro
    healthcheck:
      test: ["CMD", "mongosh", "--quiet", "--eval", "db.adminCommand('ping').ok"]
      interval: 10s
      timeout: 5s
      retries: 5
    # Sin "ports": en la VM no se expone.
```

Y en la sección `volumes:` del final: `mongo_data:`

## Solo desarrollo (docker-compose.override.yaml)

```yaml
services:
  mongo_db:
    ports:
      - "127.0.0.1:27017:27017"   # para MongoDB Compass
```

## .env (no se sube a Git) y .env.example

```
MONGO_ROOT_USER=root
MONGO_ROOT_PASSWORD=cambia_esto
MONGO_DB=sarais
MONGO_APP_USER=sarais_app
MONGO_APP_PASSWORD=cambia_esto_tambien
```
