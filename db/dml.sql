-- =====================================================================
-- SARAIS - db/dml.sql
-- Datos 100% SINTÉTICOS (nombres, documentos y teléfonos inventados).
-- Correos con dominio .test (reservado, nunca existe en Internet).
-- Contraseñas: marcador 'ARGON2_HASH_PLACEHOLDER'. La aplicación
--   genera los hashes Argon2 reales. Un marcador no es un hash válido,
--   así que nadie puede iniciar sesión hasta que la app lo reemplace.
-- Año académico 2026: periodos 1-3 cerrados (con notas), periodo 4 abierto.
-- Ejecutar DESPUÉS de ddl.sql.
-- =====================================================================

SET NAMES utf8mb4;
-- MySQL Workbench bloquea UPDATE sin clave en el WHERE; esto lo permite en esta sesión
SET SQL_SAFE_UPDATES = 0;
START TRANSACTION;

-- ---------------- roles ----------------
INSERT INTO roles (role_id, role_name, description) VALUES
 (1, 'admin',   'Directivos: gestión de usuarios, cursos y reportes'),
 (2, 'teacher', 'Profesores: registro de notas y asistencia'),
 (3, 'student', 'Estudiantes: consulta de boletín y asistencia');

-- ---------------- users ----------------
-- 1 admin, 4 profesores (2-5), 12 estudiantes (6-17)
INSERT INTO users (user_id, role_id, username, email, password_hash) VALUES
 (1,  1, 'admin.rectoria',  'admin.rectoria@sarais.test',  'ARGON2_HASH_PLACEHOLDER'),
 (2,  2, 'lgomez',          'lgomez@sarais.test',          'ARGON2_HASH_PLACEHOLDER'),
 (3,  2, 'aperez',          'aperez@sarais.test',          'ARGON2_HASH_PLACEHOLDER'),
 (4,  2, 'dcastro',         'dcastro@sarais.test',         'ARGON2_HASH_PLACEHOLDER'),
 (5,  2, 'jmoreno',         'jmoreno@sarais.test',         'ARGON2_HASH_PLACEHOLDER'),
 (6,  3, 'est.sofia.r',     'sofia.r@sarais.test',         'ARGON2_HASH_PLACEHOLDER'),
 (7,  3, 'est.mateo.l',     'mateo.l@sarais.test',         'ARGON2_HASH_PLACEHOLDER'),
 (8,  3, 'est.valentina.h', 'valentina.h@sarais.test',     'ARGON2_HASH_PLACEHOLDER'),
 (9,  3, 'est.samuel.t',    'samuel.t@sarais.test',        'ARGON2_HASH_PLACEHOLDER'),
 (10, 3, 'est.isabella.m',  'isabella.m@sarais.test',      'ARGON2_HASH_PLACEHOLDER'),
 (11, 3, 'est.nicolas.b',   'nicolas.b@sarais.test',       'ARGON2_HASH_PLACEHOLDER'),
 (12, 3, 'est.daniel.c',    'daniel.c@sarais.test',        'ARGON2_HASH_PLACEHOLDER'),
 (13, 3, 'est.mariana.o',   'mariana.o@sarais.test',       'ARGON2_HASH_PLACEHOLDER'),
 (14, 3, 'est.tomas.g',     'tomas.g@sarais.test',         'ARGON2_HASH_PLACEHOLDER'),
 (15, 3, 'est.luciana.l',   'luciana.l@sarais.test',       'ARGON2_HASH_PLACEHOLDER'),
 (16, 3, 'est.emilio.b',    'emilio.b@sarais.test',        'ARGON2_HASH_PLACEHOLDER'),
 (17, 3, 'est.antonella.n', 'antonella.n@sarais.test',     'ARGON2_HASH_PLACEHOLDER');

-- Casos de prueba de seguridad: una cuenta con intentos fallidos
-- y una bloqueada (para la consulta de cuentas bloqueadas)
UPDATE users SET failed_attempts = 3 WHERE user_id = 9;
UPDATE users SET failed_attempts = 5, locked_until = '2027-01-01 00:00:00' WHERE user_id = 12;

-- ---------------- teachers ----------------
INSERT INTO teachers (teacher_id, user_id, document_type, document_number, first_name, last_name, phone, specialty, hire_date) VALUES
 (1, 2, 'CC', '9000000001', 'Laura',  'Gómez Rincón',  '3000000101', 'Licenciatura en Matemáticas',         '2018-01-15'),
 (2, 3, 'CC', '9000000002', 'Andrés', 'Pérez Ruiz',    '3000000102', 'Licenciatura en Lengua Castellana',   '2019-01-21'),
 (3, 4, 'CC', '9000000003', 'Diana',  'Castro Vargas', '3000000103', 'Licenciatura en Ciencias Naturales',  '2020-01-20'),
 (4, 5, 'CC', '9000000004', 'Julián', 'Moreno Silva',  '3000000104', 'Licenciatura en Ciencias Sociales e Inglés', '2021-01-18');

-- ---------------- subjects ----------------
INSERT INTO subjects (subject_id, subject_code, subject_name, area, weekly_hours) VALUES
 (1, 'MAT01', 'Matemáticas',        'Matemáticas',                               5),
 (2, 'LEN01', 'Lengua Castellana',  'Humanidades',                               4),
 (3, 'ING01', 'Inglés',             'Humanidades',                               3),
 (4, 'CNA01', 'Ciencias Naturales', 'Ciencias Naturales y Educación Ambiental',  4),
 (5, 'CSO01', 'Ciencias Sociales',  'Ciencias Sociales',                         3);

-- ---------------- class_groups (año 2026) ----------------
INSERT INTO class_groups (class_group_id, academic_year, grade_level, section, homeroom_teacher_id, classroom) VALUES
 (1, 2026, 6, 'A', 1, 'Aula 101'),
 (2, 2026, 6, 'B', 2, 'Aula 102'),
 (3, 2026, 7, 'A', 3, 'Aula 201');

-- ---------------- periods ----------------
INSERT INTO periods (period_id, academic_year, period_number, start_date, end_date, weight_percent, is_closed) VALUES
 (1, 2026, 1, '2026-01-26', '2026-04-03', 25.00, 1),
 (2, 2026, 2, '2026-04-06', '2026-06-12', 25.00, 1),
 (3, 2026, 3, '2026-07-06', '2026-09-11', 25.00, 1),
 (4, 2026, 4, '2026-09-14', '2026-11-27', 25.00, 0);

-- ---------------- teaching_assignments ----------------
-- id = (curso-1)*5 + asignatura. Prof. 4 dicta Inglés y Sociales.
INSERT INTO teaching_assignments (assignment_id, teacher_id, subject_id, class_group_id) VALUES
 (1, 1, 1, 1), (2, 2, 2, 1), (3, 4, 3, 1), (4, 3, 4, 1), (5, 4, 5, 1),
 (6, 1, 1, 2), (7, 2, 2, 2), (8, 4, 3, 2), (9, 3, 4, 2), (10, 4, 5, 2),
 (11, 1, 1, 3), (12, 2, 2, 3), (13, 4, 3, 3), (14, 3, 4, 3), (15, 4, 5, 3);

-- ---------------- students ----------------
-- 6A: 1-4 | 6B: 5-8 | 7A: 9-12
INSERT INTO students (student_id, user_id, document_type, document_number, first_name, last_name, birth_date, gender, address, phone) VALUES
 (1,  6,  'TI', '1100000001', 'Sofía',     'Ramírez Torres',  '2014-03-12', 'F', 'Calle 10 # 1-01', '3100000001'),
 (2,  7,  'TI', '1100000002', 'Mateo',     'López Díaz',      '2014-07-25', 'M', 'Calle 11 # 2-02', '3100000002'),
 (3,  8,  'TI', '1100000003', 'Valentina', 'Herrera Cruz',    '2014-01-30', 'F', 'Calle 12 # 3-03', '3100000003'),
 (4,  9,  'TI', '1100000004', 'Samuel',    'Torres Medina',   '2014-11-02', 'M', 'Calle 13 # 4-04', '3100000004'),
 (5,  10, 'TI', '1100000005', 'Isabella',  'Martínez Rojas',  '2014-05-18', 'F', 'Calle 14 # 5-05', '3100000005'),
 (6,  11, 'TI', '1100000006', 'Nicolás',   'Bernal Suárez',   '2014-09-09', 'M', 'Calle 15 # 6-06', '3100000006'),
 (7,  12, 'TI', '1100000007', 'Daniel',    'Cárdenas Peña',   '2014-02-14', 'M', 'Calle 16 # 7-07', '3100000007'),
 (8,  13, 'TI', '1100000008', 'Mariana',   'Ortiz Salazar',   '2014-12-01', 'F', 'Calle 17 # 8-08', '3100000008'),
 (9,  14, 'TI', '1100000009', 'Tomás',     'García León',     '2013-04-22', 'M', 'Calle 18 # 9-09', '3100000009'),
 (10, 15, 'TI', '1100000010', 'Luciana',   'López Díaz',      '2013-08-03', 'F', 'Calle 11 # 2-02', '3100000010'),
 (11, 16, 'TI', '1100000011', 'Emilio',    'Martínez Rojas',  '2013-06-27', 'M', 'Calle 14 # 5-05', '3100000011'),
 (12, 17, 'TI', '1100000012', 'Antonella', 'Navarro Ríos',    '2013-10-15', 'F', 'Calle 19 # 1-12', '3100000012');

-- ---------------- guardians ----------------
INSERT INTO guardians (guardian_id, document_type, document_number, first_name, last_name, phone, email, address) VALUES
 (1,  'CC', '8000000001', 'Carolina', 'Torres Mejía',   '3200000001', 'carolina.t@familia.test', 'Calle 10 # 1-01'),
 (2,  'CC', '8000000002', 'Patricia', 'Díaz Acosta',    '3200000002', 'patricia.d@familia.test', 'Calle 11 # 2-02'),
 (3,  'CC', '8000000003', 'Ricardo',  'Herrera Gil',    '3200000003', NULL,                      'Calle 12 # 3-03'),
 (4,  'CC', '8000000004', 'Mónica',   'Medina Prieto',  '3200000004', 'monica.m@familia.test',   'Calle 13 # 4-04'),
 (5,  'CC', '8000000005', 'Gloria',   'Rojas Camargo',  '3200000005', NULL,                      'Calle 14 # 5-05'),
 (6,  'CC', '8000000006', 'Adriana',  'Suárez Pinto',   '3200000006', 'adriana.s@familia.test',  'Calle 15 # 6-06'),
 (7,  'CC', '8000000007', 'Fernando', 'Cárdenas Mora',  '3200000007', 'fernando.c@familia.test', 'Calle 16 # 7-07'),
 (8,  'CC', '8000000008', 'Liliana',  'Salazar Vega',   '3200000008', 'liliana.s@familia.test',  'Calle 17 # 8-08'),
 (9,  'CE', '8000000009', 'Héctor',   'León Fajardo',   '3200000009', 'hector.l@familia.test',   'Calle 18 # 9-09'),
 (10, 'CC', '8000000010', 'Natalia',  'Ríos Guerrero',  '3200000010', 'natalia.r@familia.test',  'Calle 19 # 1-12');

-- ---------------- student_guardians ----------------
-- Hermanos: 2 y 10 (acudiente 2), 5 y 11 (acudiente 5).
-- Acudiente 7 es papá del est. 7 y tío (secundario) del est. 8.
INSERT INTO student_guardians (student_id, guardian_id, relationship, is_primary) VALUES
 (1, 1, 'mother', 1),
 (2, 2, 'mother', 1),
 (3, 3, 'father', 1),
 (4, 4, 'mother', 1),
 (5, 5, 'grandparent', 1),
 (6, 6, 'mother', 1),
 (7, 7, 'father', 1),
 (8, 8, 'mother', 1),
 (8, 7, 'uncle_aunt', 0),
 (9, 9, 'legal_guardian', 1),
 (10, 2, 'mother', 1),
 (11, 5, 'grandparent', 1),
 (12, 10, 'mother', 1);

-- ---------------- enrollments ----------------
INSERT INTO enrollments (enrollment_id, student_id, class_group_id, enrollment_date, status) VALUES
 (1, 1, 1, '2026-01-19', 'active'), (2, 2, 1, '2026-01-19', 'active'),
 (3, 3, 1, '2026-01-19', 'active'), (4, 4, 1, '2026-01-19', 'active'),
 (5, 5, 2, '2026-01-19', 'active'), (6, 6, 2, '2026-01-19', 'active'),
 (7, 7, 2, '2026-01-19', 'active'), (8, 8, 2, '2026-01-19', 'active'),
 (9, 9, 3, '2026-01-19', 'active'), (10, 10, 3, '2026-01-19', 'active'),
 (11, 11, 3, '2026-01-19', 'active'), (12, 12, 3, '2026-01-19', 'active');

-- ---------------- grades ----------------
-- Se generan con una fórmula determinista (siempre da los mismos valores):
-- nota = 2.5 + MOD(7*matrícula + 13*asignatura + 5*periodo, 26) / 10  -> rango 2.5 a 5.0
-- Solo para periodos cerrados y solo asignaturas del curso del estudiante.
INSERT INTO grades (enrollment_id, assignment_id, period_id, score)
SELECT e.enrollment_id,
       ta.assignment_id,
       p.period_id,
       ROUND(2.5 + MOD(e.enrollment_id * 7 + ta.subject_id * 13 + p.period_id * 5, 26) / 10, 1)
FROM enrollments e
JOIN teaching_assignments ta ON ta.class_group_id = e.class_group_id
JOIN periods p ON p.academic_year = 2026 AND p.is_closed = 1;

-- Caso de estudio: el estudiante 7 (matrícula 7) tiene bajo rendimiento
UPDATE grades SET score = GREATEST(score - 1.0, 0) WHERE enrollment_id = 7;

UPDATE grades
   SET observation = 'Desempeño bajo: requiere plan de mejoramiento'
 WHERE score < 3.0;

-- ---------------- attendance ----------------
-- 6 fechas de clase (martes): 2 por periodo cerrado y 1 del periodo 4.
-- Estado generado con fórmula determinista (mayoría 'present').
INSERT INTO attendance (enrollment_id, assignment_id, class_date, status)
SELECT e.enrollment_id,
       ta.assignment_id,
       d.class_date,
       CASE MOD(e.enrollment_id * 3 + ta.subject_id * 2 + DAY(d.class_date), 13)
            WHEN 0 THEN 'absent'
            WHEN 1 THEN 'late'
            WHEN 2 THEN 'excused'
            ELSE 'present'
       END
FROM enrollments e
JOIN teaching_assignments ta ON ta.class_group_id = e.class_group_id
CROSS JOIN (
    SELECT DATE('2026-02-10') AS class_date UNION ALL
    SELECT DATE('2026-03-17') UNION ALL
    SELECT DATE('2026-05-05') UNION ALL
    SELECT DATE('2026-06-02') UNION ALL
    SELECT DATE('2026-08-11') UNION ALL
    SELECT DATE('2026-10-06')
) AS d;

-- Coherente con sus notas: el estudiante 7 falta más
UPDATE attendance
   SET status = 'absent', notes = 'Inasistencia sin justificar'
 WHERE enrollment_id = 7
   AND class_date IN ('2026-03-17', '2026-05-05', '2026-08-11')
   AND status = 'present';

COMMIT;
