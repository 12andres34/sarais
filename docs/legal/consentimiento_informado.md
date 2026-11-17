# Plantilla: Autorización para el tratamiento de datos personales de estudiantes

> Plantilla académica (proyecto SARAIS). Los campos entre `[corchetes]` se completan por la institución. Debe revisarla un abogado antes de usarla con datos reales.

---

**[NOMBRE DE LA INSTITUCIÓN EDUCATIVA]**
NIT: [________] · Dirección: [________], Tunja, Boyacá · Correo para datos personales: [________]

## AUTORIZACIÓN PARA EL TRATAMIENTO DE DATOS PERSONALES DE NIÑOS, NIÑAS Y ADOLESCENTES

En cumplimiento de la **Ley Estatutaria 1581 de 2012** y del **Decreto 1377 de 2013** (compilado en el Decreto 1074 de 2015), yo:

- Nombre del acudiente / representante legal: ______________________________
- Documento de identidad: ______ No. ________________
- Parentesco o calidad: ☐ Padre ☐ Madre ☐ Tutor legal ☐ Otro: ________

actuando como representante legal del estudiante:

- Nombre del estudiante: ______________________________
- Documento de identidad: ______ No. ________________
- Grado: ______

**AUTORIZO** de manera **previa, expresa e informada** a [NOMBRE DE LA INSTITUCIÓN], como **Responsable del Tratamiento**, para recolectar, almacenar, usar y actualizar los datos personales del estudiante y los míos, en los siguientes términos:

### 1. Datos que se tratarán
- **Del estudiante:** nombres, apellidos, tipo y número de documento, fecha de nacimiento, grado y grupo, calificaciones, asistencia y documentos académicos.
- **Del acudiente:** nombres, apellidos, documento, parentesco, teléfono y correo electrónico.
- **No** se recogen datos sensibles (salud, biometría, origen étnico, creencias). Si en el futuro fueran necesarios, se pedirá una autorización aparte, y su entrega será **facultativa**.

### 2. Finalidades
Los datos se usarán **únicamente** para:
a) Gestionar la matrícula, los grupos y las asignaturas.
b) Registrar y consultar calificaciones y asistencia.
c) Generar boletines académicos.
d) Comunicarse con el acudiente sobre asuntos académicos.
e) Cumplir obligaciones legales del sector educativo.

No se usarán para publicidad ni se venderán ni cederán a terceros, salvo por orden de autoridad competente.

### 3. Interés superior del menor
El tratamiento responde y respeta el **interés superior** del estudiante y asegura el respeto de sus **derechos fundamentales**. El estudiante fue escuchado y su opinión fue tenida en cuenta según su madurez, autonomía y capacidad de entender el asunto.

### 4. Medidas de seguridad
La información se guarda en el sistema SARAIS con: conexiones cifradas (HTTPS/TLS), bases de datos cifradas, contraseñas protegidas, verificación en dos pasos para el personal, acceso por roles (cada docente ve solo sus grupos), registro de auditoría y copias de seguridad cifradas.

### 5. Derechos del titular (art. 8, Ley 1581 de 2012)
Como representante del estudiante y como titular de mis propios datos, puedo:
- Conocer, actualizar y rectificar los datos.
- Solicitar prueba de esta autorización.
- Ser informado sobre el uso que se ha dado a los datos.
- Presentar quejas ante la **Superintendencia de Industria y Comercio**.
- Revocar esta autorización o solicitar la supresión de los datos, cuando no exista un deber legal o contractual de conservarlos. (Los registros académicos tienen deber de conservación.)
- Acceder gratuitamente a los datos.

### 6. Cómo ejercer estos derechos
- Correo: [________] · Presencial: [dirección y horario]
- **Consultas:** respuesta en máximo **10 días hábiles**.
- **Reclamos:** respuesta en máximo **15 días hábiles**.
- Política de tratamiento de datos: [enlace o lugar donde se consulta].

### 7. Vigencia
Esta autorización está vigente mientras el estudiante tenga vínculo con la institución y durante el tiempo que exija la ley para conservar los registros académicos.

---

**Opinión del estudiante** (según su edad y madurez): ☐ Fue informado y está de acuerdo ☐ Fue informado y expresó lo siguiente: ________________________

Firma del acudiente: __________________________ Fecha: ____ / ____ / ______

Firma del estudiante (opcional según edad): __________________________

Recibido por (institución): __________________________ Cargo: ____________

---
*Uso en SARAIS:* el formato firmado se escanea y se sube como documento. El sistema lo cifra con GPG (`documents/<uuid>.gpg`), registra sus metadatos sin datos personales en `document_metadata` y deja el evento `document_uploaded` en `audit_logs`.
