# Deployment notes per release

Read this before installing an update on the server. `scripts\make-usb.ps1` copies it next to the `recruitment-agent` folder in every `usb_x_y_z` release.

The release package contains **no `.env`**. When a release needs a setting added or changed, it is listed below under that version, and you make the change on the server by hand. Apply the settings for every version newer than the one in `VERSION.txt`, oldest first. `.env.example` in the package lists every key.

---

## 0.1.0

**Server settings:** first install. Create `.env` using `scripts\2-install-offline.ps1`, then set `DB_*`, `LLM_*`, `HOST`, `PORT`, `TLS_CERT_FILE` and `TLS_KEY_FILE` as described in DEPLOY.md §3.

**Server prerequisites:** Python 3.11 x64, and ODBC Driver 17 or 18 for SQL Server.

**Database (once, by a DBA):** run `sql\02_agent_memory.sql` in the database that holds the `T_IIR_ARIF_*` tables. It creates the app's own table `T_IIR_ARIF_AGENT_MEMORY` (idempotent). Grant the app login `SELECT` on `T_IIR_ARIF_CANDIDATE`, `T_IIR_ARIF_EDUCATION`, `T_IIR_ARIF_EXPERIENCE` and `T_IIR_ARIF_SKILLS`, plus `SELECT, INSERT, UPDATE, DELETE` on `T_IIR_ARIF_AGENT_MEMORY`. `/api/health` shows `db.memory_table: true` when the table is there.

**Optional (recommended at 350k+ candidates):** ask the owner of the `T_IIR_ARIF_*` tables to run `sql\03_recommended_indexes.sql`. The app works without it.

**Reference data:** `data\reference\application_statuses.csv` maps status codes to stages and to "open for matching". The shipped file is a placeholder; replace it with the real list (same columns) and restart the app.

**What changed:** initial release.
