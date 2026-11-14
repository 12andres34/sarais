// db/mongo/scripts/audit_logs_crud.js
// audit_logs es solo-agregar: aquí solo hay CREATE y READ.
// Se ejecuta con el usuario de la app.

const col = db.audit_logs;

// --- CREATE ---
col.insertMany([
  {
    user_id: NumberInt(2),
    action: 'LOGIN_SUCCESS',
    timestamp: new Date(),
    source_ip: '192.168.56.1',
    result: 'SUCCESS'
  },
  {
    user_id: null,  // usuario inexistente: no se guarda el texto que escribió
    action: 'LOGIN_FAILED',
    timestamp: new Date(),
    source_ip: '192.168.56.20',
    result: 'FAILURE',
    details: { reason: 'unknown_user' }
  },
  {
    user_id: NumberInt(2),
    action: 'GRADE_UPDATE',
    timestamp: new Date(),
    source_ip: '192.168.56.1',
    result: 'SUCCESS',
    details: { grade_id: 15, old_value: 3.5, new_value: 4.0 }
  }
]);
print('CREATE -> 3 eventos insertados');

// --- READ ---
print('READ: últimos 5 eventos');
col.find({}, { _id: 0 }).sort({ timestamp: -1 }).limit(5).forEach(printjson);

print('READ: eventos del usuario 2');
col.find({ user_id: NumberInt(2) }, { _id: 0, action: 1, timestamp: 1 }).forEach(printjson);

print('READ: intentos fallidos por IP en las últimas 24 h');
col.aggregate([
  { $match: { action: 'LOGIN_FAILED', timestamp: { $gte: new Date(Date.now() - 24 * 3600 * 1000) } } },
  { $group: { _id: '$source_ip', attempts: { $sum: 1 } } },
  { $sort: { attempts: -1 } }
]).forEach(printjson);

// Comprueba que la consulta usa el índice (IXSCAN = búsqueda por índice)
const plan = JSON.stringify(col.find({ action: 'LOGIN_FAILED' }).explain().queryPlanner.winningPlan);
print('¿Usa índice idx_audit_action?', plan.includes('IXSCAN'));
