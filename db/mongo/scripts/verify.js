// db/mongo/scripts/verify.js
// Pruebas de seguridad. Se ejecuta con el usuario de la APP (no con root).
// Cada prueba debe imprimir PASS.
//   121 = DocumentValidationFailure (JSON Schema)
//   13  = Unauthorized (falta de privilegio)

let failures = 0;

// Obtiene el código de error, venga directo o dentro de writeErrors
function errorCode(e) {
  if (e.code !== undefined) return e.code;
  if (e.writeErrors && e.writeErrors.length) return e.writeErrors[0].code;
  return undefined;
}

function expectError(name, expectedCode, fn) {
  try {
    fn();
    print(`FAIL  ${name}: la operación fue aceptada`);
    failures++;
  } catch (e) {
    const code = errorCode(e);
    if (code === expectedCode) {
      print(`PASS  ${name} (código ${code})`);
    } else {
      print(`FAIL  ${name}: código inesperado ${code} - ${e.message}`);
      failures++;
    }
  }
}

function expectOk(name, fn) {
  try { fn(); print(`PASS  ${name}`); }
  catch (e) { print(`FAIL  ${name}: ${e.message}`); failures++; }
}

const valid = {
  user_id: NumberInt(1), action: 'LOGOUT', timestamp: new Date(),
  source_ip: '10.0.0.5', result: 'SUCCESS'
};

print('--- Validación con JSON Schema ---');
expectOk('insert válido en audit_logs', () => db.audit_logs.insertOne({ ...valid }));

expectError('rechaza action fuera del enum', 121, () =>
  db.audit_logs.insertOne({ ...valid, action: 'HACK' }));

expectError('rechaza documento sin campo obligatorio (result)', 121, () => {
  const d = { ...valid }; delete d.result; db.audit_logs.insertOne(d);
});

expectError('rechaza timestamp como texto', 121, () =>
  db.audit_logs.insertOne({ ...valid, timestamp: '2026-11-14' }));

expectError('rechaza campo extra con dato personal (email)', 121, () =>
  db.audit_logs.insertOne({ ...valid, email: 'x@example.com' }));

expectError('rechaza nombre dentro de details', 121, () =>
  db.audit_logs.insertOne({ ...valid, details: { name: 'Synthetic Name' } }));

expectError('rechaza storage_path sin cifrar (.pdf)', 121, () =>
  db.document_metadata.insertOne({
    type: 'REPORT_CARD', upload_date: new Date(),
    uploader_id: NumberInt(1), student_ref: NumberInt(1),
    storage_path: 'documents/boletin_juan.pdf'
  }));

print('--- audit_logs es solo-agregar para la app ---');
expectError('no puede hacer updateOne', 13, () =>
  db.audit_logs.updateOne({ action: 'LOGOUT' }, { $set: { result: 'FAILURE' } }));

expectError('no puede hacer replaceOne', 13, () =>
  db.audit_logs.replaceOne({ action: 'LOGOUT' }, { ...valid, result: 'FAILURE' }));

expectError('no puede hacer deleteMany', 13, () =>
  db.audit_logs.deleteMany({}));

expectError('no puede hacer drop', 13, () =>
  db.runCommand({ drop: 'audit_logs' }));

expectError('no puede quitar el validador (collMod)', 13, () =>
  db.runCommand({ collMod: 'audit_logs', validator: {} }));

expectOk('sí puede leer (find)', () => db.audit_logs.findOne());

print(failures === 0 ? '\nRESULTADO: todas las pruebas PASS' : `\nRESULTADO: ${failures} prueba(s) FAIL`);
