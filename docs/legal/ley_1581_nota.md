# Nota: Ley 1581 de 2012 y SARAIS

> Resumen académico, no asesoría legal. Para una implementación real, la institución debe validar su política con un abogado.
> SARAIS usa **solo datos sintéticos**. Esta nota explica qué exigiría la ley si se usara con datos reales.

## 1. Marco legal

- **Ley Estatutaria 1581 de 2012:** régimen general de protección de datos personales en Colombia (habeas data, art. 15 de la Constitución).
- **Decreto 1377 de 2013:** la reglamenta. Hoy está compilado en el **Decreto Único 1074 de 2015** (Título 2.2.2.25).
- **Sentencia C-748 de 2011** de la Corte Constitucional: revisó la ley antes de su expedición.
- **Autoridad:** Superintendencia de Industria y Comercio (SIC), Delegatura para la Protección de Datos Personales.

## 2. Lo esencial para un colegio

| Tema | Qué dice | Cómo lo atiende SARAIS |
|---|---|---|
| **Datos de menores** (art. 7) | La ley prohíbe tratar datos de niños, niñas y adolescentes, salvo los de naturaleza pública. La Corte (C-748/2011) y el Decreto 1377 (art. 12) lo permiten si el tratamiento **responde y respeta el interés superior del menor** y **asegura sus derechos fundamentales**. El representante legal da la autorización, después de escuchar la opinión del menor según su madurez. | Solo se recogen datos necesarios para la gestión académica. El acudiente firma el consentimiento (plantilla en este directorio). |
| **Autorización** (art. 9) | Previa, expresa e informada. Hay que poder **probarla** después. | Consentimiento firmado y archivado como documento cifrado (GPG). Su registro queda en `document_metadata` y `audit_logs`. |
| **Datos sensibles** (art. 5 y 6) | Salud, biometría, origen étnico, etc. Su entrega es **facultativa**. | SARAIS **no** guarda datos sensibles: ni salud ni biometría. |
| **Finalidad** (art. 4) | Se usan solo para lo que se informó. | Finalidad única: gestión académica (matrículas, notas, asistencia, boletines). Sin pagos ni mercadeo. |
| **Seguridad** (art. 4 lit. g y art. 17) | Medidas técnicas para evitar pérdida, consulta o acceso no autorizado. | TLS, cifrado en reposo, Argon2id, MFA, roles, auditoría, backups cifrados (ver `security_design.md`). |
| **Acceso restringido** (art. 4 lit. f) | Solo personas autorizadas. | Matriz de roles; docentes ven solo sus grupos (`access_control.md`). |
| **Derechos del titular** (art. 8) | Conocer, actualizar, rectificar, pedir prueba de la autorización, ser informado del uso, quejarse ante la SIC, revocar la autorización o pedir supresión (cuando no exista un deber legal de conservar), y acceder gratis. | El admin puede consultar y corregir. La supresión se hace desactivando la cuenta, porque el registro académico tiene deber de conservación. |
| **Consultas** (art. 14) | Respuesta en máximo **10 días hábiles** (prorrogables 5). | Procedimiento a cargo del área administrativa. |
| **Reclamos** (art. 15) | Respuesta en máximo **15 días hábiles**. | Ídem. |
| **Política de tratamiento** (Decreto 1377, art. 13) | Obligatoria, por escrito y publicada. | Pendiente para una implementación real. |
| **Registro Nacional de Bases de Datos (RNBD)** | Solo obligatorio para ciertos responsables, según su tamaño (umbral de activos). | Verificar con la SIC según los activos de la institución. |

## 3. Datos que guarda SARAIS (minimización)

| Dato | ¿Necesario? | Dónde |
|---|---|---|
| Nombre, documento, fecha de nacimiento, grupo | Sí: identifica al estudiante y define su matrícula | MySQL cifrado |
| Nombre y contacto del acudiente | Sí: comunicación con la familia | MySQL cifrado |
| Notas, asistencia | Sí: finalidad principal | MySQL cifrado |
| Documentos (p. ej. consentimiento firmado) | Sí: prueba de la autorización | `.gpg` + metadatos sin datos personales |
| Salud, religión, biometría, fotos | **No** | No se recogen |

## 4. Incidentes

Si ocurre una violación de seguridad que ponga en riesgo los datos, el responsable debe informar a la SIC (art. 17 lit. n). Para eso, el plan de SARAIS se apoya en:

1. `audit_logs` y `docker logs`: qué pasó, cuándo y con qué cuenta.
2. `restore.sh`: recuperar los datos.
3. Cambio de contraseñas y llaves (`.env`) y reinicio de MFA.
