-- =====================================================================
-- SARAIS - db/queries.sql
-- 12 consultas de negocio. Ejecutar después de ddl.sql y dml.sql.
-- Cada consulta indica qué técnica SQL demuestra.
-- =====================================================================

-- Q1. Listado de estudiantes con su curso y acudiente principal
-- Técnica: JOIN de 5 tablas
SELECT CONCAT(cg.grade_level, cg.section)     AS class_group,
       s.document_number,
       CONCAT(s.last_name, ' ', s.first_name) AS student,
       CONCAT(g.first_name, ' ', g.last_name) AS primary_guardian,
       sg.relationship,
       g.phone                                AS guardian_phone
FROM students s
JOIN enrollments e        ON e.student_id = s.student_id
JOIN class_groups cg      ON cg.class_group_id = e.class_group_id
JOIN student_guardians sg ON sg.student_id = s.student_id AND sg.is_primary = 1
JOIN guardians g          ON g.guardian_id = sg.guardian_id
WHERE cg.academic_year = 2026
ORDER BY class_group, student;

-- Q2. Promedio, nota máxima y mínima por asignatura y periodo
-- Técnica: AVG, MAX, MIN, GROUP BY
SELECT p.period_number,
       sub.subject_name,
       ROUND(AVG(gr.score), 2) AS avg_score,
       MAX(gr.score)           AS max_score,
       MIN(gr.score)           AS min_score,
       COUNT(*)                AS grades_count
FROM grades gr
JOIN teaching_assignments ta ON ta.assignment_id = gr.assignment_id
JOIN subjects sub            ON sub.subject_id = ta.subject_id
JOIN periods p               ON p.period_id = gr.period_id
GROUP BY p.period_number, sub.subject_name
ORDER BY p.period_number, sub.subject_name;

-- Q3. Estudiantes en riesgo académico: promedio del periodo menor a 3.0
-- Técnica: GROUP BY + HAVING
SELECT p.period_number,
       CONCAT(s.last_name, ' ', s.first_name) AS student,
       ROUND(AVG(gr.score), 2)                AS period_avg
FROM grades gr
JOIN enrollments e ON e.enrollment_id = gr.enrollment_id
JOIN students s    ON s.student_id = e.student_id
JOIN periods p     ON p.period_id = gr.period_id
GROUP BY p.period_number, s.student_id, s.last_name, s.first_name
HAVING AVG(gr.score) < 3.0
ORDER BY p.period_number, period_avg;

-- Q4. Estudiantes con 3 o más fallas (ausencias) en el año
-- Técnica: COUNT + filtro WHERE + HAVING
SELECT CONCAT(cg.grade_level, cg.section)     AS class_group,
       CONCAT(s.last_name, ' ', s.first_name) AS student,
       COUNT(*)                               AS absences
FROM attendance a
JOIN enrollments e   ON e.enrollment_id = a.enrollment_id
JOIN students s      ON s.student_id = e.student_id
JOIN class_groups cg ON cg.class_group_id = e.class_group_id
WHERE a.status = 'absent'
GROUP BY cg.grade_level, cg.section, s.student_id, s.last_name, s.first_name
HAVING COUNT(*) >= 3
ORDER BY absences DESC;

-- Q5. Carga académica de cada profesor
-- Técnica: LEFT JOIN, COUNT, SUM, COUNT(DISTINCT)
SELECT CONCAT(t.first_name, ' ', t.last_name) AS teacher,
       COUNT(ta.assignment_id)                AS assignments,
       COUNT(DISTINCT ta.class_group_id)      AS groups_taught,
       COALESCE(SUM(sub.weekly_hours), 0)     AS weekly_hours
FROM teachers t
LEFT JOIN teaching_assignments ta ON ta.teacher_id = t.teacher_id
LEFT JOIN subjects sub            ON sub.subject_id = ta.subject_id
GROUP BY t.teacher_id, t.first_name, t.last_name
ORDER BY weekly_hours DESC;

-- Q6. Estudiantes cuyo promedio anual supera el promedio institucional
-- Técnica: subconsulta escalar dentro de HAVING
SELECT CONCAT(s.last_name, ' ', s.first_name) AS student,
       ROUND(AVG(gr.score), 2)                AS student_avg
FROM grades gr
JOIN enrollments e ON e.enrollment_id = gr.enrollment_id
JOIN students s    ON s.student_id = e.student_id
GROUP BY s.student_id, s.last_name, s.first_name
HAVING AVG(gr.score) > (SELECT AVG(score) FROM grades)
ORDER BY student_avg DESC;

-- Q7. Mejor estudiante de cada curso (promedio más alto)
-- Técnica: tabla derivada + subconsulta correlacionada con MAX
SELECT x.class_group, x.student, x.student_avg
FROM (
    SELECT e.class_group_id,
           CONCAT(cg.grade_level, cg.section)     AS class_group,
           CONCAT(s.last_name, ' ', s.first_name) AS student,
           ROUND(AVG(gr.score), 2)                AS student_avg
    FROM grades gr
    JOIN enrollments e   ON e.enrollment_id = gr.enrollment_id
    JOIN students s      ON s.student_id = e.student_id
    JOIN class_groups cg ON cg.class_group_id = e.class_group_id
    GROUP BY e.class_group_id, cg.grade_level, cg.section, s.student_id, s.last_name, s.first_name
) AS x
WHERE x.student_avg = (
    SELECT MAX(y.avg_score)
    FROM (
        SELECT e2.class_group_id, ROUND(AVG(g2.score), 2) AS avg_score
        FROM grades g2
        JOIN enrollments e2 ON e2.enrollment_id = g2.enrollment_id
        GROUP BY e2.class_group_id, e2.student_id
    ) AS y
    WHERE y.class_group_id = x.class_group_id
)
ORDER BY x.class_group;

-- Q8. Nota final acumulada por asignatura (ponderada por peso del periodo)
-- Técnica: SUM ponderada / SUM de pesos, solo periodos cerrados
SELECT CONCAT(s.last_name, ' ', s.first_name)                        AS student,
       sub.subject_name,
       ROUND(SUM(gr.score * p.weight_percent) / SUM(p.weight_percent), 2) AS weighted_avg,
       COUNT(*)                                                       AS periods_graded
FROM grades gr
JOIN periods p               ON p.period_id = gr.period_id AND p.is_closed = 1
JOIN enrollments e           ON e.enrollment_id = gr.enrollment_id
JOIN students s              ON s.student_id = e.student_id
JOIN teaching_assignments ta ON ta.assignment_id = gr.assignment_id
JOIN subjects sub            ON sub.subject_id = ta.subject_id
GROUP BY s.student_id, s.last_name, s.first_name, sub.subject_id, sub.subject_name
ORDER BY student, sub.subject_name;

-- Q9. Asignaciones con notas pendientes en el periodo abierto
-- Técnica: subconsulta NOT EXISTS
SELECT CONCAT(cg.grade_level, cg.section)     AS class_group,
       sub.subject_name,
       CONCAT(t.first_name, ' ', t.last_name) AS teacher
FROM teaching_assignments ta
JOIN class_groups cg ON cg.class_group_id = ta.class_group_id
JOIN subjects sub    ON sub.subject_id = ta.subject_id
JOIN teachers t      ON t.teacher_id = ta.teacher_id
WHERE NOT EXISTS (
    SELECT 1
    FROM grades gr
    JOIN periods p ON p.period_id = gr.period_id
    WHERE gr.assignment_id = ta.assignment_id
      AND p.is_closed = 0
)
ORDER BY class_group, sub.subject_name;

-- Q10. Porcentaje de asistencia por curso
-- Técnica: SUM(CASE ...) + COUNT, agregación condicional
SELECT CONCAT(cg.grade_level, cg.section) AS class_group,
       COUNT(*)                           AS records,
       SUM(CASE WHEN a.status IN ('present', 'late') THEN 1 ELSE 0 END) AS attended,
       ROUND(100 * SUM(CASE WHEN a.status IN ('present', 'late') THEN 1 ELSE 0 END) / COUNT(*), 1)
                                          AS attendance_pct
FROM attendance a
JOIN enrollments e   ON e.enrollment_id = a.enrollment_id
JOIN class_groups cg ON cg.class_group_id = e.class_group_id
GROUP BY cg.class_group_id, cg.grade_level, cg.section
ORDER BY attendance_pct DESC;

-- Q11. Acudientes con más de un estudiante a cargo
-- Técnica: GROUP BY + HAVING COUNT > 1 + GROUP_CONCAT
SELECT CONCAT(g.first_name, ' ', g.last_name) AS guardian,
       COUNT(*)                               AS students_count,
       GROUP_CONCAT(CONCAT(s.first_name, ' ', s.last_name) ORDER BY s.first_name SEPARATOR ', ') AS students
FROM guardians g
JOIN student_guardians sg ON sg.guardian_id = g.guardian_id
JOIN students s           ON s.student_id = sg.student_id
GROUP BY g.guardian_id, g.first_name, g.last_name
HAVING COUNT(*) > 1;

-- Q12. Cuentas bloqueadas o con intentos fallidos (control de seguridad)
-- Técnica: JOIN + condiciones con NULL y NOW()
SELECT u.username,
       r.role_name,
       u.failed_attempts,
       u.locked_until,
       CASE WHEN u.locked_until > NOW() THEN 'LOCKED' ELSE 'WARNING' END AS account_state
FROM users u
JOIN roles r ON r.role_id = u.role_id
WHERE u.failed_attempts > 0
   OR u.locked_until > NOW()
ORDER BY u.failed_attempts DESC;

-- Q13. Boletín de un estudiante (usa la vista v_report_card)
-- Técnica: consulta sobre VIEW
SELECT period_number, subject_name, teacher_name, score, performance_level, absences
FROM v_report_card
WHERE student_id = 7
ORDER BY period_number, subject_name;
