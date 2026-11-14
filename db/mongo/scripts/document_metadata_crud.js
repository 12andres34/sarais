// db/mongo/scripts/document_metadata_crud.js
// CRUD completo sobre document_metadata. Se ejecuta con el usuario de la app.
// Nota: en mongosh los números son double; por eso se usa NumberInt() para los IDs.

const col = db.document_metadata;

// --- CREATE ---
const created = col.insertOne({
  type: 'ENROLLMENT_FORM',
  upload_date: new Date(),
  uploader_id: NumberInt(1),   // users.id (admin)
  student_ref: NumberInt(1),   // students.id
  storage_path: 'documents/3f2a9c1e-7b4d-4e8a-9f10-2c6d8e4b5a71.gpg'
});
const docId = created.insertedId;
print('CREATE ->', docId);

// --- READ ---
print('READ (por id):');
printjson(col.findOne({ _id: docId }));

print('READ (documentos del estudiante 1, más recientes primero):');
col.find({ student_ref: NumberInt(1) }, { _id: 1, type: 1, upload_date: 1 })
   .sort({ upload_date: -1 })
   .forEach(printjson);

// --- UPDATE ---
const updated = col.updateOne(
  { _id: docId },
  { $set: { type: 'OTHER', updated_at: new Date() } }
);
print('UPDATE -> modificados:', updated.modifiedCount);
printjson(col.findOne({ _id: docId }, { type: 1, updated_at: 1 }));

// --- DELETE ---
const deleted = col.deleteOne({ _id: docId });
print('DELETE -> borrados:', deleted.deletedCount);
print('Comprobación, debe ser null:', col.findOne({ _id: docId }));
