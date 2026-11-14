# MongoDB in SARAIS

## Why MongoDB alongside MySQL

1. MySQL stores the structured academic core (students, grades, attendance) that needs 3NF, joins and referential integrity; MongoDB stores only audit events and document metadata.
2. Audit events have a variable `details` field (a grade change, a failed login, a backup) that fits a flexible document better than many nullable columns or extra tables.
3. Audit logs are write-heavy and append-only; a separate store keeps this load and its retention away from the transactional academic database.
4. A custom MongoDB role grants only `insert` and `find` on `audit_logs`, so the application can never edit or delete its own audit trail, which separates duties from MySQL.
5. Flexibility is controlled: `$jsonSchema` validators, enums and indexes reject malformed or personal data, and documents link to MySQL only by numeric IDs (`user_id`, `student_ref`).

## Encryption at rest: limitation and compensating controls

MongoDB Community Edition does not include the Encrypted Storage Engine (Enterprise only). SARAIS compensates as follows:

- **Data minimization:** no names or personal data are stored in MongoDB, only numeric IDs, enums, dates and IPs. The validator blocks common personal-data keys.
- **Files encrypted with GPG:** documents are stored as `.gpg` files; the validator only accepts `storage_path` values with a random UUID name and `.gpg` extension.
- **Encrypted backups:** `mongodump` output is encrypted with GPG by `backup.sh` before it is stored.
- **Reduced exposure:** MongoDB has authentication enabled, runs only on the internal Docker network, and its port is not published on the VM.
- **Least privilege:** the application user has a custom role with no `update`, `remove`, `drop` or `collMod` on `audit_logs`.
- **Optional extra layer:** full-disk encryption of the VM (LUKS) would protect the data volume itself; it is not required by the current design.

Residual risk: a user with root access to the VM or to MongoDB could read or alter the data files. This risk is recorded in the risk matrix and is mitigated by SSH key access, restricted Linux groups, and encrypted backups.
