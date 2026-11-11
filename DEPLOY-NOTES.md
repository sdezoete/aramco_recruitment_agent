# Deployment notes per release

Read this before installing an update on the server. `scripts\make-usb.ps1` copies it next to the `recruitment-agent` folder in every `usb_x_y_z` release.

The release package contains **no `.env`**. When a release needs a setting added or changed, it is listed below under that version, and you make the change on the server by hand. Apply the settings for every version newer than the one in `VERSION.txt`, oldest first. `.env.example` in the package lists every key.

---

## 0.1.0

**Server settings:** first install. Create `.env` using `scripts\2-install-offline.ps1`, then set `DB_*`, `LLM_*`, `HOST`, `PORT`, `TLS_CERT_FILE` and `TLS_KEY_FILE` as described in DEPLOY.md §3.

**Server prerequisites:** Python 3.11 x64, and ODBC Driver 17 or 18 for SQL Server.

**What changed:** initial release.
