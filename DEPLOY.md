# Deploying the Recruitment Agent on the air-gapped server

This file follows [docs/AIRGAP_DEPLOYMENT_STANDARD.md](docs/AIRGAP_DEPLOYMENT_STANDARD.md). Per-release server settings are in [DEPLOY-NOTES.md](DEPLOY-NOTES.md).

## 1. Server prerequisites (bring the installers on the USB stick)

- Windows Server x64 with **Python 3.11 x64** (`python-3.11.x-amd64.exe`)
- **Microsoft ODBC Driver 17 (or 18) for SQL Server** (`msodbcsql.msi`). If the server has 18, set `DB_DRIVER=ODBC Driver 18 for SQL Server` and review `DB_ENCRYPT`.
- Network access from the server to the SQL Server instance and to the MaaS gateway
- The organisation's TLS certificate (PEM certificate with the chain, plus the key)

## 2. What is on the USB stick

`usb_x_y_z\recruitment-agent\` (git-tracked files + `wheels\` + `VERSION.txt`) and `usb_x_y_z\DEPLOY-NOTES.md`. There is no `.env`: the server keeps its own.

## 3. First install

```powershell
# copy recruitment-agent to e.g. D:\recruitment-agent, then:
cd D:\recruitment-agent
powershell -ExecutionPolicy Bypass -File scripts\2-install-offline.ps1
```

The script:
- finds Python 3.11
- creates `.venv`
- installs from `wheels\` with no internet access
- runs `pip check`
- creates `.env` from `.env.example` with `PRODUCTION=True`, if it doesn't exist yet
- lists the installed ODBC drivers

Then edit `.env`:
- `DB_*`: the production SQL Server
- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`: the gateway. List the model ids with `Invoke-RestMethod <LLM_BASE_URL>/models -Headers @{Authorization="Bearer <key>"}`
- `HOST=0.0.0.0`, `PORT`, `TLS_CERT_FILE`, `TLS_KEY_FILE`

## 4. Start and check

```bat
scripts\run-server.bat
```

Open `https://<server name on the certificate>:<PORT>/api/health`. It must show `production: true`, `db.reachable: true` and `llm.reachable: true`, together with the LLM capabilities.

## 5. Update

1. Stop the app.
2. Rename `D:\recruitment-agent` to `D:\recruitment-agent-prev`.
3. Copy the new `recruitment-agent` folder from the USB stick.
4. Copy `.env` (and `certs\`, if used) back from `-prev`.
5. Apply the **Server settings** in `DEPLOY-NOTES.md` for every version newer than `-prev\VERSION.txt`.
6. Run `scripts\2-install-offline.ps1`, start the app, and check `/api/health` and `VERSION.txt`.

## 6. Rollback

Stop the app, rename the current folder to `-bad`, rename `-prev` back, and start the app.
