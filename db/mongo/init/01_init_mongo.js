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
appDb.createCollection('audit_logs', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      title: 'audit_logs',
      required: ['user_id', 'action', 'timestamp', 'source_ip', 'result'],
      additionalProperties: false,
      properties: {
        _id: { bsonType: 'objectId' },
        // users.id de MySQL; null si el login falla con un usuario inexistente
        user_id: { bsonType: ['int', 'long', 'null'], minimum: 1 },
        action: {
          enum: [
            'LOGIN_SUCCESS', 'LOGIN_FAILED', 'LOGOUT',
            'MFA_SUCCESS', 'MFA_FAILED', 'ACCOUNT_LOCKED',
            'USER_CREATE', 'USER_UPDATE', 'ROLE_CHANGE',
            'GRADE_CREATE', 'GRADE_UPDATE',
            'ATTENDANCE_CREATE', 'ATTENDANCE_UPDATE',
            'DOCUMENT_UPLOAD', 'DOCUMENT_DOWNLOAD', 'DOCUMENT_UPDATE', 'DOCUMENT_DELETE',
            'ACCESS_DENIED', 'BACKUP_RUN'
          ]
        },
        timestamp: { bsonType: 'date' },
        // 45 caracteres alcanza para IPv6
        source_ip: { bsonType: 'string', minLength: 3, maxLength: 45 },
        result: { enum: ['SUCCESS', 'FAILURE', 'DENIED'] },
        // Datos extra (ej. grade_id, old_value). Se bloquean claves con datos personales.
        details: {
          bsonType: 'object',
          maxProperties: 20,
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
