// db/mongo/scripts/migrate_audit_validator.js
// Actualiza el validador de audit_logs a la v2 en un volumen YA creado
// (01_init_mongo.js solo corre con el volumen vacío).
// Se ejecuta como ROOT: el rol de la app no tiene collMod, a propósito.
//   docker exec -it mongo_db sh -c 'mongosh -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" \
//     --authenticationDatabase admin "$MONGO_INITDB_DATABASE" --quiet /scripts/migrate_audit_validator.js'
// Los eventos viejos (MAYÚSCULAS, source_ip) se quedan como están: la auditoría no se reescribe.
// La pantalla /admin/audit ya sabe leer ambos formatos (audit_service.list_logs).

const auditSchema = {
  $jsonSchema: {
    bsonType: 'object',
    title: 'audit_logs v2',
    required: ['timestamp', 'user_id', 'action', 'ip', 'result', 'details'],
    additionalProperties: false,
    properties: {
      _id: { bsonType: 'objectId' },
      timestamp: { bsonType: 'date' },
      user_id: { bsonType: ['int', 'long', 'null'], minimum: 1 },
      action: {
        enum: [
          'login_success', 'login_failed', 'mfa_failed', 'mfa_enabled', 'mfa_reset',
          'account_locked', 'logout', 'user_created', 'user_updated',
          'enrollment_created', 'enrollment_updated', 'grade_change',
          'attendance_recorded', 'document_uploaded'
        ]
      },
      ip: { bsonType: ['string', 'null'], maxLength: 45 },
      result: { enum: ['success', 'failure'] },
      details: {
        bsonType: 'object',
        maxProperties: 10,
        additionalProperties: {
          bsonType: ['int', 'long', 'double', 'bool', 'null', 'string'],
          pattern: '^[A-Za-z0-9_./-]{1,64}$'
        },
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
};

const res = db.runCommand({
  collMod: 'audit_logs', validator: auditSchema,
  validationLevel: 'strict', validationAction: 'error'
});
if (res.ok !== 1) throw new Error('collMod falló: ' + JSON.stringify(res));
print('[migrate] validador de audit_logs actualizado a v2');

// Autoverificación. En mongosh un número suelto es double: los IDs van con NumberInt.
// (pymongo ya envía los int de Python como int.) Los documentos de prueba se borran al final.
const ids = [];
function tryInsert(label, doc, shouldPass) {
  try {
    ids.push(db.audit_logs.insertOne(doc).insertedId);
    print((shouldPass ? '[migrate] PASS aceptado: ' : '[migrate] FAIL se aceptó: ') + label);
  } catch (e) {
    const code = e.code ?? (e.writeErrors && e.writeErrors[0].code);
    print((shouldPass ? '[migrate] FAIL rechazado: ' : `[migrate] PASS rechazado (${code}): `) + label);
  }
}
const base = { timestamp: new Date(), user_id: NumberInt(1), action: 'grade_change',
               ip: '10.0.0.1', result: 'success', details: {} };

tryInsert('grade_change con IDs y notas', { ...base, details: {
  enrollment_id: NumberInt(5), assignment_id: NumberInt(2), period_id: NumberInt(1),
  old_score: 3.5, new_score: 4.0 } }, true);
tryInsert('login_failed de usuario inexistente', { ...base, user_id: null, action: 'login_failed',
  ip: null, result: 'failure', details: { reason: 'unknown_user' } }, true);
tryInsert('attendance_recorded con fecha', { ...base, action: 'attendance_recorded',
  details: { assignment_id: NumberInt(2), class_date: '2026-11-17', records: NumberInt(20) } }, true);
tryInsert('acción vieja en MAYÚSCULAS', { ...base, action: 'LOGOUT' }, false);
tryInsert('result booleano', { ...base, result: true }, false);
tryInsert('texto libre en details', { ...base, details: { comment: 'Nombre Apellido 2.0' } }, false);
tryInsert('clave personal en details', { ...base, details: { email: 'x' } }, false);
tryInsert('campo extra (source_ip)', { ...base, source_ip: '10.0.0.1' }, false);

db.audit_logs.deleteMany({ _id: { $in: ids } });
print('[migrate] listo. Documentos de prueba borrados: ' + ids.length);
