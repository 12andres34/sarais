-- =====================================================================
-- SARAIS - Secure and Reliable Academic Information System
-- Archivo: db/ddl.sql
-- Motor: MySQL 8.4 | InnoDB | utf8mb4
-- Contenido: 13 tablas en 3FN + vista v_report_card (boletín)
-- Nota: este script NO crea la base de datos ni usuarios.
--   - En Docker, el entrypoint lo ejecuta sobre MYSQL_DATABASE (.env).
--   - Los GRANTs y el usuario de mínimo privilegio los define el chat de seguridad.
-- =====================================================================

SET NAMES utf8mb4;

-- Borrado en orden inverso a las dependencias (permite re-ejecutar el script)
DROP VIEW  IF EXISTS v_report_card;
DROP TABLE IF EXISTS attendance;
DROP TABLE IF EXISTS grades;
DROP TABLE IF EXISTS enrollments;
DROP TABLE IF EXISTS teaching_assignments;
DROP TABLE IF EXISTS periods;
DROP TABLE IF EXISTS class_groups;
DROP TABLE IF EXISTS subjects;
DROP TABLE IF EXISTS teachers;
DROP TABLE IF EXISTS student_guardians;
DROP TABLE IF EXISTS guardians;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS roles;

-- ---------------------------------------------------------------------
-- 1. roles: catálogo de roles del sistema (RBAC)
-- ---------------------------------------------------------------------
CREATE TABLE roles (
    role_id      TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    role_name    VARCHAR(20)      NOT NULL,
    description  VARCHAR(150)     NULL,
    CONSTRAINT pk_roles PRIMARY KEY (role_id),
    CONSTRAINT uq_roles_name UNIQUE (role_name),
    CONSTRAINT ck_roles_name CHECK (role_name IN ('admin', 'teacher', 'student'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------
-- 2. users: cuentas de acceso (autenticación, MFA, bloqueo)
-- ---------------------------------------------------------------------
CREATE TABLE users (
    user_id               INT UNSIGNED     NOT NULL AUTO_INCREMENT,
    role_id               TINYINT UNSIGNED NOT NULL,
    username              VARCHAR(50)      NOT NULL,
    email                 VARCHAR(120)     NOT NULL,
    password_hash         VARCHAR(255)     NOT NULL,          -- hash Argon2 generado por la app
    mfa_enabled           TINYINT(1)       NOT NULL DEFAULT 0,
    mfa_secret_encrypted  VARBINARY(512)   NULL,              -- secreto TOTP ya cifrado por la app
    failed_attempts       TINYINT UNSIGNED NOT NULL DEFAULT 0,
    locked_until          DATETIME         NULL,              -- NULL = cuenta no bloqueada
    is_active             TINYINT(1)       NOT NULL DEFAULT 1,
    last_login_at         DATETIME         NULL,
    created_at            DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT pk_users PRIMARY KEY (user_id),
    CONSTRAINT uq_users_username UNIQUE (username),
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT fk_users_role FOREIGN KEY (role_id)
        REFERENCES roles (role_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT ck_users_mfa_flag CHECK (mfa_enabled IN (0, 1)),
    CONSTRAINT ck_users_active_flag CHECK (is_active IN (0, 1)),
    -- si MFA está activo, debe existir el secreto cifrado
    CONSTRAINT ck_users_mfa_secret CHECK (mfa_enabled = 0 OR mfa_secret_encrypted IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------
-- 3. students: datos personales del estudiante (solo en MySQL)
-- ---------------------------------------------------------------------
CREATE TABLE students (
    student_id       INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id          INT UNSIGNED NULL,                 -- cuenta de acceso (opcional)
    document_type    CHAR(2)      NOT NULL,             -- TI, RC, CE, PA
    document_number  VARCHAR(20)  NOT NULL,
    first_name       VARCHAR(60)  NOT NULL,
    last_name        VARCHAR(60)  NOT NULL,
    birth_date       DATE         NOT NULL,
    gender           CHAR(1)      NOT NULL,
    address          VARCHAR(150) NULL,
    phone            VARCHAR(20)  NULL,
    status           VARCHAR(12)  NOT NULL DEFAULT 'active',
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_students PRIMARY KEY (student_id),
    CONSTRAINT uq_students_user UNIQUE (user_id),
    CONSTRAINT uq_students_document UNIQUE (document_type, document_number),
    CONSTRAINT fk_students_user FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT ck_students_doc_type CHECK (document_type IN ('TI', 'RC', 'CE', 'PA')),
    CONSTRAINT ck_students_gender CHECK (gender IN ('F', 'M', 'O')),
    CONSTRAINT ck_students_status CHECK (status IN ('active', 'inactive', 'graduated', 'withdrawn'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX idx_students_name ON students (last_name, first_name);

-- ---------------------------------------------------------------------
-- 4. guardians: acudientes
-- ---------------------------------------------------------------------
CREATE TABLE guardians (
    guardian_id      INT UNSIGNED NOT NULL AUTO_INCREMENT,
    document_type    CHAR(2)      NOT NULL,             -- CC, CE, PA
    document_number  VARCHAR(20)  NOT NULL,
    first_name       VARCHAR(60)  NOT NULL,
    last_name        VARCHAR(60)  NOT NULL,
    phone            VARCHAR(20)  NOT NULL,
    email            VARCHAR(120) NULL,
    address          VARCHAR(150) NULL,
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_guardians PRIMARY KEY (guardian_id),
    CONSTRAINT uq_guardians_document UNIQUE (document_type, document_number),
    CONSTRAINT ck_guardians_doc_type CHECK (document_type IN ('CC', 'CE', 'PA'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX idx_guardians_name ON guardians (last_name, first_name);

-- ---------------------------------------------------------------------
-- 5. student_guardians: relación N:M estudiante-acudiente
-- ---------------------------------------------------------------------
CREATE TABLE student_guardians (
    student_id    INT UNSIGNED NOT NULL,
    guardian_id   INT UNSIGNED NOT NULL,
    relationship  VARCHAR(15)  NOT NULL,
    is_primary    TINYINT(1)   NOT NULL DEFAULT 0,      -- acudiente principal
    CONSTRAINT pk_student_guardians PRIMARY KEY (student_id, guardian_id),
    CONSTRAINT fk_sg_student FOREIGN KEY (student_id)
        REFERENCES students (student_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_sg_guardian FOREIGN KEY (guardian_id)
        REFERENCES guardians (guardian_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT ck_sg_relationship CHECK (relationship IN
        ('mother', 'father', 'grandparent', 'sibling', 'uncle_aunt', 'legal_guardian', 'other')),
    CONSTRAINT ck_sg_primary CHECK (is_primary IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------
-- 6. teachers: profesores (el correo de acceso vive en users)
-- ---------------------------------------------------------------------
CREATE TABLE teachers (
    teacher_id       INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id          INT UNSIGNED NULL,
    document_type    CHAR(2)      NOT NULL,             -- CC, CE, PA
    document_number  VARCHAR(20)  NOT NULL,
    first_name       VARCHAR(60)  NOT NULL,
    last_name        VARCHAR(60)  NOT NULL,
    phone            VARCHAR(20)  NULL,
    specialty        VARCHAR(80)  NOT NULL,
    hire_date        DATE         NOT NULL,
    is_active        TINYINT(1)   NOT NULL DEFAULT 1,
    CONSTRAINT pk_teachers PRIMARY KEY (teacher_id),
    CONSTRAINT uq_teachers_user UNIQUE (user_id),
    CONSTRAINT uq_teachers_document UNIQUE (document_type, document_number),
    CONSTRAINT fk_teachers_user FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT ck_teachers_doc_type CHECK (document_type IN ('CC', 'CE', 'PA')),
    CONSTRAINT ck_teachers_active CHECK (is_active IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------
-- 7. subjects: asignaturas
-- ---------------------------------------------------------------------
CREATE TABLE subjects (
    subject_id    SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    subject_code  VARCHAR(10)       NOT NULL,
    subject_name  VARCHAR(80)       NOT NULL,
    area          VARCHAR(60)       NOT NULL,           -- área del plan de estudios
    weekly_hours  TINYINT UNSIGNED  NOT NULL,
    CONSTRAINT pk_subjects PRIMARY KEY (subject_id),
    CONSTRAINT uq_subjects_code UNIQUE (subject_code),
    CONSTRAINT uq_subjects_name UNIQUE (subject_name),
    CONSTRAINT ck_subjects_hours CHECK (weekly_hours BETWEEN 1 AND 10)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------
-- 8. class_groups: cursos (ej. grado 6, sección A, año 2026)
--    No se usa "groups": es palabra reservada en MySQL 8.
--    El nombre "6A" NO se guarda: se deriva de grade_level + section.
-- ---------------------------------------------------------------------
CREATE TABLE class_groups (
    class_group_id       INT UNSIGNED      NOT NULL AUTO_INCREMENT,
    academic_year        SMALLINT UNSIGNED NOT NULL,
    grade_level          TINYINT UNSIGNED  NOT NULL,    -- 0 = transición ... 11
    section              CHAR(1)           NOT NULL,    -- A, B, C...
    homeroom_teacher_id  INT UNSIGNED      NULL,        -- director de grupo
    classroom            VARCHAR(20)       NULL,
    CONSTRAINT pk_class_groups PRIMARY KEY (class_group_id),
    CONSTRAINT uq_class_groups UNIQUE (academic_year, grade_level, section),
    CONSTRAINT fk_cg_homeroom FOREIGN KEY (homeroom_teacher_id)
        REFERENCES teachers (teacher_id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT ck_cg_year CHECK (academic_year BETWEEN 2000 AND 2100),
    CONSTRAINT ck_cg_grade CHECK (grade_level BETWEEN 0 AND 11),
    CONSTRAINT ck_cg_section CHECK (section BETWEEN 'A' AND 'Z')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------
-- 9. periods: periodos académicos del año
-- ---------------------------------------------------------------------
CREATE TABLE periods (
    period_id       TINYINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    academic_year   SMALLINT UNSIGNED NOT NULL,
    period_number   TINYINT UNSIGNED  NOT NULL,
    start_date      DATE              NOT NULL,
    end_date        DATE              NOT NULL,
    weight_percent  DECIMAL(5,2)      NOT NULL,         -- peso del periodo en la nota final
    is_closed       TINYINT(1)        NOT NULL DEFAULT 0,
    CONSTRAINT pk_periods PRIMARY KEY (period_id),
    CONSTRAINT uq_periods UNIQUE (academic_year, period_number),
    CONSTRAINT ck_periods_number CHECK (period_number BETWEEN 1 AND 4),
    CONSTRAINT ck_periods_dates CHECK (end_date > start_date),
    CONSTRAINT ck_periods_weight CHECK (weight_percent > 0 AND weight_percent <= 100),
    CONSTRAINT ck_periods_closed CHECK (is_closed IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------
-- 10. teaching_assignments: qué profesor dicta qué asignatura en qué curso
-- ---------------------------------------------------------------------
CREATE TABLE teaching_assignments (
    assignment_id   INT UNSIGNED      NOT NULL AUTO_INCREMENT,
    teacher_id      INT UNSIGNED      NOT NULL,
    subject_id      SMALLINT UNSIGNED NOT NULL,
    class_group_id  INT UNSIGNED      NOT NULL,
    CONSTRAINT pk_teaching_assignments PRIMARY KEY (assignment_id),
    -- una asignatura tiene un solo profesor por curso
    CONSTRAINT uq_ta_subject_group UNIQUE (subject_id, class_group_id),
    CONSTRAINT fk_ta_teacher FOREIGN KEY (teacher_id)
        REFERENCES teachers (teacher_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_ta_subject FOREIGN KEY (subject_id)
        REFERENCES subjects (subject_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_ta_group FOREIGN KEY (class_group_id)
        REFERENCES class_groups (class_group_id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------
-- 11. enrollments: matrícula de un estudiante en un curso
-- ---------------------------------------------------------------------
CREATE TABLE enrollments (
    enrollment_id    INT UNSIGNED NOT NULL AUTO_INCREMENT,
    student_id       INT UNSIGNED NOT NULL,
    class_group_id   INT UNSIGNED NOT NULL,
    enrollment_date  DATE         NOT NULL,
    status           VARCHAR(10)  NOT NULL DEFAULT 'active',
    CONSTRAINT pk_enrollments PRIMARY KEY (enrollment_id),
    CONSTRAINT uq_enrollments UNIQUE (student_id, class_group_id),
    CONSTRAINT fk_enr_student FOREIGN KEY (student_id)
        REFERENCES students (student_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_enr_group FOREIGN KEY (class_group_id)
        REFERENCES class_groups (class_group_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT ck_enr_status CHECK (status IN ('active', 'withdrawn', 'completed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------
-- 12. grades: nota de un estudiante, en una asignatura, en un periodo
-- ---------------------------------------------------------------------
CREATE TABLE grades (
    grade_id       INT UNSIGNED     NOT NULL AUTO_INCREMENT,
    enrollment_id  INT UNSIGNED     NOT NULL,
    assignment_id  INT UNSIGNED     NOT NULL,
    period_id      TINYINT UNSIGNED NOT NULL,
    score          DECIMAL(3,2)     NOT NULL,           -- escala 0.00 a 5.00
    observation    VARCHAR(255)     NULL,
    recorded_at    DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT pk_grades PRIMARY KEY (grade_id),
    -- una sola nota por estudiante/asignatura/periodo
    CONSTRAINT uq_grades UNIQUE (enrollment_id, assignment_id, period_id),
    CONSTRAINT fk_grades_enrollment FOREIGN KEY (enrollment_id)
        REFERENCES enrollments (enrollment_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_grades_assignment FOREIGN KEY (assignment_id)
        REFERENCES teaching_assignments (assignment_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_grades_period FOREIGN KEY (period_id)
        REFERENCES periods (period_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT ck_grades_score CHECK (score BETWEEN 0 AND 5)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------
-- 13. attendance: asistencia por clase (el periodo se deduce de la fecha)
-- ---------------------------------------------------------------------
CREATE TABLE attendance (
    attendance_id  INT UNSIGNED NOT NULL AUTO_INCREMENT,
    enrollment_id  INT UNSIGNED NOT NULL,
    assignment_id  INT UNSIGNED NOT NULL,
    class_date     DATE         NOT NULL,
    status         VARCHAR(8)   NOT NULL,
    notes          VARCHAR(255) NULL,
    recorded_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_attendance PRIMARY KEY (attendance_id),
    CONSTRAINT uq_attendance UNIQUE (enrollment_id, assignment_id, class_date),
    CONSTRAINT fk_att_enrollment FOREIGN KEY (enrollment_id)
        REFERENCES enrollments (enrollment_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_att_assignment FOREIGN KEY (assignment_id)
        REFERENCES teaching_assignments (assignment_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT ck_att_status CHECK (status IN ('present', 'absent', 'late', 'excused'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE INDEX idx_attendance_date ON attendance (class_date);

-- =====================================================================
-- VISTA: v_report_card (boletín)
-- Una fila por estudiante + periodo + asignatura, con nivel de desempeño
-- y número de fallas (ausencias) dentro de las fechas del periodo.
-- Escala de desempeño (ejemplo institucional):
--   Bajo < 3.0 | Básico 3.0-3.99 | Alto 4.0-4.59 | Superior >= 4.6
-- =====================================================================
CREATE VIEW v_report_card AS
SELECT
    p.academic_year,
    p.period_number,
    CONCAT(cg.grade_level, cg.section)           AS class_group,
    s.student_id,
    s.document_number                            AS student_document,
    CONCAT(s.last_name, ' ', s.first_name)       AS student_name,
    sub.subject_name,
    sub.area,
    CONCAT(t.first_name, ' ', t.last_name)       AS teacher_name,
    g.score,
    CASE
        WHEN g.score >= 4.6 THEN 'Superior'
        WHEN g.score >= 4.0 THEN 'Alto'
        WHEN g.score >= 3.0 THEN 'Basico'
        ELSE 'Bajo'
    END                                          AS performance_level,
    (SELECT COUNT(*)
       FROM attendance a
      WHERE a.enrollment_id = g.enrollment_id
        AND a.assignment_id = g.assignment_id
        AND a.status = 'absent'
        AND a.class_date BETWEEN p.start_date AND p.end_date) AS absences,
    g.observation
FROM grades g
JOIN enrollments          e   ON e.enrollment_id   = g.enrollment_id
JOIN students             s   ON s.student_id      = e.student_id
JOIN class_groups         cg  ON cg.class_group_id = e.class_group_id
JOIN teaching_assignments ta  ON ta.assignment_id  = g.assignment_id
JOIN subjects             sub ON sub.subject_id    = ta.subject_id
JOIN teachers             t   ON t.teacher_id      = ta.teacher_id
JOIN periods              p   ON p.period_id       = g.period_id;

-- =====================================================================
-- CIFRADO EN REPOSO (pendiente del chat de seguridad)
-- ENCRYPTION='Y' falla si el keyring no está configurado.
-- Cuando el keyring esté activo, descomentar este bloque
-- (o ejecutarlo aparte). Verificar con:
--   SELECT NAME, ENCRYPTION FROM information_schema.INNODB_TABLESPACES
--   WHERE NAME LIKE CONCAT(DATABASE(), '/%');
-- =====================================================================
-- ALTER TABLE roles                ENCRYPTION='Y';
-- ALTER TABLE users                ENCRYPTION='Y';
-- ALTER TABLE students             ENCRYPTION='Y';
-- ALTER TABLE guardians            ENCRYPTION='Y';
-- ALTER TABLE student_guardians    ENCRYPTION='Y';
-- ALTER TABLE teachers             ENCRYPTION='Y';
-- ALTER TABLE subjects             ENCRYPTION='Y';
-- ALTER TABLE class_groups         ENCRYPTION='Y';
-- ALTER TABLE periods              ENCRYPTION='Y';
-- ALTER TABLE teaching_assignments ENCRYPTION='Y';
-- ALTER TABLE enrollments          ENCRYPTION='Y';
-- ALTER TABLE grades               ENCRYPTION='Y';
-- ALTER TABLE attendance           ENCRYPTION='Y';
