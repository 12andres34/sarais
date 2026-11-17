// db/mongo/init/01_init_mongo.js
// Se ejecuta UNA sola vez, cuando el volumen de MongoDB está vacío.
// Lo corre el entrypoint oficial de mongo:7 con el usuario root.
// Crea: colecciones con JSON Schema, índices, rol personalizado y usuario de la app.

// --- 1. Leer variables de entorno (nunca contraseñas en el código) ---
const dbName = process.env.MONGO_INITDB_DATABASE || 'sarais';
const appUser = process.env.MONGO_APP_USER;
const appPassword = process.env.MONGO_APP_PASSWORD;

if (!appUser || !appPassword) {
  throw new Error('MONGO_APP_USER y MONGO_APP_PASSWORD son obligatorios (.env)');
}

const appDb = db.getSiblingDB(dbName);

// --- 2. Colección audit_logs ---
// Solo IDs de MySQL; nada de nombres, correos ni documentos de identidad.
// Formato v2 (chat de Seguridad): lo escribe app/security/audit.py.
// Mismo esquema en db/mongo/scripts/migrate_audit_validator.js (para volúmenes ya creados).
appDb.createCollection('audit_logs', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      title: 'audit_logs v2',
      required: ['timestamp', 'user_id', 'action', 'ip', 'result', 'details'],
      additionalProperties: false,
      properties: {
        _id: { bsonType: 'objectId' },
        timestamp: { bsonType: 'date' },
        // users.user_id de MySQL; null si el login falla con un usuario inexistente
        user_id: { bsonType: ['int', 'long', 'null'], minimum: 1 },
        action: {
          enum: [
            'login_success', 'login_failed', 'mfa_failed', 'mfa_enabled', 'mfa_reset',
            'account_locked', 'logout', 'user_created', 'user_updated',
            'enrollment_created', 'enrollment_updated', 'grade_change',
            'attendance_recorded', 'document_uploaded'
          ]
        },
        // 45 caracteres alcanza para IPv6; null si no se conoce
        ip: { bsonType: ['string', 'null'], maxLength: 45 },
        result: { enum: ['success', 'failure'] },
        // Solo IDs, números y códigos cortos sin espacios (nunca texto libre)
        details: {
          bsonType: 'object',
          maxProperties: 10,
          additionalProperties: {
            bsonType: ['int', 'long', 'double', 'bool', 'null', 'string'],
            pattern: '^[A-Za-z0-9_./-]{1,64}$'
          },
          // Segunda barrera: claves típicas de datos personales prohibidas
          not: {
            anyOf: [
              { required: ['name'] }, { required: ['first_name'] },
              { required: ['last_name'] }, { required: ['email'] },
              { required: ['password'] }, { required: ['document_number'] },
              { required: ['phone'] }, { required: ['address'] }
            ]
          }
        }
      }
    }
  },
  validationLevel: 'strict',  // valida todos los inserts
  validationAction: 'error'   // rechaza el documento (no solo avisa)
});

// --- 3. Colección document_metadata ---
// El archivo real está cifrado con GPG en disco; aquí solo va su metadato.
appDb.createCollection('document_metadata', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      title: 'document_metadata',
      required: ['type', 'upload_date', 'uploader_id', 'student_ref', 'storage_path'],
      additionalProperties: false,
      properties: {
        _id: { bsonType: 'objectId' },
        type: {
          enum: ['ENROLLMENT_FORM', 'REPORT_CARD', 'ID_DOCUMENT', 'MEDICAL_EXCUSE', 'OTHER']
        },
        upload_date: { bsonType: 'date' },
        uploader_id: { bsonType: ['int', 'long'], minimum: 1 },  // users.id
        student_ref: { bsonType: ['int', 'long'], minimum: 1 },  // students.id
        // Nombre aleatorio (UUID) + extensión .gpg: obliga a que el archivo esté cifrado
        // y evita nombres de estudiantes en la ruta.
        storage_path: {
          bsonType: 'string',
          pattern: '^documents/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\.gpg$'
        },
        updated_at: { bsonType: 'date' }  // opcional, lo pone la app al actualizar
      }
    }
  },
  validationLevel: 'strict',
  validationAction: 'error'
});

// --- 4. Índices ---
appDb.audit_logs.createIndex({ user_id: 1 }, { name: 'idx_audit_user_id' });
appDb.audit_logs.createIndex({ action: 1 }, { name: 'idx_audit_action' });
appDb.audit_logs.createIndex({ timestamp: -1 }, { name: 'idx_audit_timestamp' });

appDb.document_metadata.createIndex({ student_ref: 1 }, { name: 'idx_doc_student_ref' });
appDb.document_metadata.createIndex({ uploader_id: 1 }, { name: 'idx_doc_uploader_id' });
appDb.document_metadata.createIndex({ storage_path: 1 }, { name: 'uq_doc_storage_path', unique: true });

// --- 5. Rol personalizado de mínimo privilegio ---
// audit_logs: solo insert y find (solo-agregar). Sin update, remove, drop ni collMod.
// document_metadata: CRUD completo.
appDb.createRole({
  role: 'saraisAppRole',
  privileges: [
    {
      resource: { db: dbName, collection: 'audit_logs' },
      actions: ['find', 'insert']
    },
    {
      resource: { db: dbName, collection: 'document_metadata' },
      actions: ['find', 'insert', 'update', 'remove']
    }
  ],
  roles: []  // no hereda ningún rol integrado (ni readWrite)
});

// --- 6. Usuario de la aplicación ---
appDb.createUser({
  user: appUser,
  pwd: appPassword,
  roles: [{ role: 'saraisAppRole', db: dbName }],
  mechanisms: ['SCRAM-SHA-256']
});

print(`[init] Base '${dbName}' lista: colecciones, índices, rol y usuario '${appUser}'.`);
