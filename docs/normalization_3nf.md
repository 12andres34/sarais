# SARAIS — Normalization Justification (up to 3NF)

## 1. Definitions used

- **1NF**: every column holds one atomic value; no repeating groups; every table has a primary key.
- **2NF**: 1NF + no non-key column depends on only *part* of a composite key.
- **3NF**: 2NF + no non-key column depends on another non-key column (no *transitive* dependency).

## 2. Starting point: one flat "report card" sheet

A school often keeps everything in a single spreadsheet like this (synthetic data):

| student_doc | student_name | guardian_name | guardian_phone | group | homeroom_teacher | subject | teacher | teacher_phone | period | period_start | score |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1100000001 | Sofía Ramírez | Carolina Torres, Ricardo Herrera | 3200000001, 3200000003 | 6A | Laura Gómez | Matemáticas | Laura Gómez | 3000000101 | 1 | 2026-01-26 | 4.5 |
| 1100000001 | Sofía Ramírez | Carolina Torres, Ricardo Herrera | 3200000001, 3200000003 | 6A | Laura Gómez | Inglés | Julián Moreno | 3000000104 | 1 | 2026-01-26 | 3.8 |

Problems:
- **Update anomaly**: if a teacher changes phone, many rows must change.
- **Insert anomaly**: a new subject cannot be stored until someone gets a grade in it.
- **Delete anomaly**: deleting the last grade of a student deletes the guardian's data too.

## 3. Step to 1NF
`guardian_name` and `guardian_phone` hold lists (not atomic). Guardians move to their own table, and the many-to-many link becomes `student_guardians (student_id, guardian_id, relationship, is_primary)`.

## 4. Step to 2NF
Take the natural key of a grade: `(student_doc, subject, period)`.

| Dependency | Problem | Fix |
|---|---|---|
| `student_doc → student_name, birth_date` | Depends on part of the key | Table `students` |
| `subject → area, weekly_hours` | Depends on part of the key | Table `subjects` |
| `period → period_start, period_end` | Depends on part of the key | Table `periods` |

After this, `grades` keeps only what depends on the **whole** key: `score` and `observation`. Its unique key is `(enrollment_id, assignment_id, period_id)`.

## 5. Step to 3NF — removed transitive dependency (main example)

In the 2NF `grades` table we still had:

```
grade_id → (subject, group) → teacher → teacher_phone
```

`teacher` does not depend directly on the grade. It depends on the pair *(subject, group)*: whoever teaches Mathematics in 6A teaches it to every student of 6A. And `teacher_phone` depends on `teacher`. These are **transitive dependencies**.

**Fix:**
1. `teacher_phone` (and every teacher attribute) moves to `teachers`.
2. The fact "who teaches what to whom" moves to `teaching_assignments (teacher_id, subject_id, class_group_id)` with `UNIQUE (subject_id, class_group_id)`.
3. `grades` stores only `assignment_id`.

Result: changing the Mathematics teacher of 6A is **one UPDATE** in `teaching_assignments`, not one per grade.

## 6. Other 3NF decisions in the schema

| Decision | Transitive dependency avoided |
|---|---|
| `class_groups` does not store a name like "6A" | `class_group_id → (grade_level, section) → name`. The name is derived in queries and in the view. |
| `attendance` does not store `period_id` | `class_date → period_id` (via the period dates). Storing it could contradict the date. |
| `enrollments` does not store `academic_year` | `class_group_id → academic_year`. It is read from `class_groups`. |
| `teachers` and `students` do not repeat the login email | `user_id → email`. The email lives only in `users`. |
| `users` stores `role_id`, not the role name | `role_id → role_name`. Role names live only in `roles`. |
| `v_report_card` computes `performance_level` | `score → performance_level`. A derived value is never stored, so it cannot become inconsistent. |

## 7. Check of the final tables

For each of the 13 tables, every non-key column describes **the key, the whole key, and nothing but the key**:

- Tables with a single-column surrogate PK (`users`, `students`, `grades`, …) satisfy 2NF automatically. Natural keys are kept as `UNIQUE` constraints (e.g. `UQ (document_type, document_number)`).
- The only table with a composite PK, `student_guardians`, has non-key columns (`relationship`, `is_primary`) that depend on the full pair: the same guardian can be "father" of one student and "uncle_aunt" of another (guardian 7 in the sample data).
- `username` and `email` in `users` are both candidate keys (UNIQUE). A dependency between two candidate keys does not break 3NF.

## 8. Accepted limitation
Some cross-table rules cannot be expressed with simple foreign keys without adding redundant columns (for example: the assignment in `grades` must belong to the same group as the enrollment). We keep the schema in 3NF and enforce these rules in the application layer (see `data_dictionary.md`).
