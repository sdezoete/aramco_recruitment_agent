# Air-Gapped Deployment Standard (instructions for Claude)

> Reusable across projects. Copy this file into a new project's `docs/` and add the line
> `@docs/AIRGAP_DEPLOYMENT_STANDARD.md` to that project's `CLAUDE.md`. Project-specific values
> (app folder name, port, server path) belong in that project's `CLAUDE.md` and `DEPLOY.md`, not here.

When a project follows this standard, every rule below is a hard requirement. If a request conflicts with a rule, say so before doing the work.

---

## 1. The two environments

| | Development machine | Production server |
|---|---|---|
| OS / Python | Windows x64, **Python 3.11 x64** (must match the server) | Windows Server x64, Python 3.11 x64 |
| Internet | Full access | **None (air-gapped)**: no PyPI, no CDN, no public APIs |
| `.env` | `PRODUCTION=False` | `PRODUCTION=True` |
| Code changes | All development and testing happen here | **Never edit code on the server** |
| LLM | Any reachable OpenAI-compatible endpoint (dev stand-in) | Corporate OpenAI-compatible gateway (internal URL, internal CA) |

Code moves in one direction only: **dev machine → `usb_x_y_z` folder → USB stick → server.**

## 2. Dependencies: wheels only

- Every third-party Python dependency must ship as a **`.whl`** in `wheels/`. Never ship a source archive (`.tar.gz`, `.zip`, `.tar.bz2`). Build those into wheels on the dev machine first, using `pip wheel`.
- The wheels must be for the **server's** platform: `win_amd64` and `cp311`, or `abi3` / `py3-none-any`. The dev machine runs the same Python 3.11 x64, so `pip wheel` there produces compatible wheels.
- `requirements.txt` lists top-level dependencies pinned with `==`. The wheel build resolves and includes every transitive dependency.
- **Keep the dependency count low.** Before adding a package, check whether the standard library covers the need. Packages with native extensions need a cp311 win_amd64 wheel. Note every new package in `DECISIONS.md` and in `DEPLOY-NOTES.md`.
- Anything that cannot be a wheel (ODBC drivers, VC++ runtimes, the Python installer) is a **server prerequisite**. List it in `DEPLOY.md` and bring the installer on the same USB stick.
- After building `wheels/`, verify it: no non-`.whl` files, an offline install into a fresh venv (`pip install --no-index --find-links wheels -r requirements.txt`) succeeds, `pip check` is clean, and the app's import smoke test passes.

## 3. Frontend: fully self-contained

- Plain HTML, CSS and JavaScript. No build step, no CDNs, no web fonts from the internet, and no external URLs at runtime.
- Third-party JS/CSS libraries (for example Chart.js) are **vendored** into `static/vendor/<lib>-<exact version>/` together with their license file. Record the version in `static/vendor/VENDORED.md`.
- Use a strict Content-Security-Policy (`default-src 'self'`). The browser talks only to this server.

## 4. Configuration: `.env` and the `PRODUCTION` switch

- `.env` sits next to the app entry point. The app reads it itself, and its values override machine environment variables of the same name.
- **`PRODUCTION=False`** on the dev machine. **`PRODUCTION=True`** on the server. If the value is missing or blank, the app treats it as `False` and prints a loud banner saying so.
- `PRODUCTION=True` must enforce all of the following:
  - HTTPS with the organisation's certificate; self-signed and expired certificates are refused
  - no debug mode and no auto-reload
  - no stack traces in HTTP responses
  - LLM TLS verification on, with the internal CA trusted through the Windows certificate store or a configured CA file
  - refusal to start if a required setting is missing
- **`.env` is never committed and never shipped.** `.env.example` is committed. It documents every key with a safe default and contains no secrets. On a first install, `2-install-offline.ps1` creates the server's `.env` from `.env.example` with `PRODUCTION=True`, and never overwrites an existing one.
- At startup, log the effective configuration (secrets masked) and a reachability check for each external dependency: the database and the LLM.

## 5. LLM access

- Use one **OpenAI-compatible** chat-completions client (`<base>/chat/completions`, Bearer token) for both environments. Only `.env` values change between them: `LLM_BASE_URL` (ends in `/v1`), `LLM_API_KEY`, `LLM_MODEL` (the gateway's exact id), `LLM_VERIFY_SSL`, `LLM_TIMEOUT_SECONDS`.
- Do not assume that every gateway feature is supported. Probe at startup for function calling (`tools`), `stream`, and `response_format`. When a feature is missing, fall back gracefully: for example, prompted JSON tool calls instead of native `tools`. When a request is rejected, retry it without the optional parameter.
- Ignore proxy environment variables for internal LLM calls by default.
- If the LLM is unreachable, the app still runs, falls back to rules where possible, and labels that output clearly.
- Treat uploaded files and database text as **data, not instructions**, to guard against prompt injection.

## 6. Versioning and release (on the dev machine)

1. Make the change and run the tests.
2. Bump `__version__` in the app package (`x.y.z`).
3. Add a `## x.y.z` section to `DEPLOY-NOTES.md`. It lists **every `.env` key the server must add or change**, plus any new server prerequisite. If there is nothing, write `**Server settings:** none.`
4. If `requirements.txt` changed, run `scripts\1-build-wheels.ps1`.
5. Commit and tag `vx.y.z`.
6. Run `scripts\make-usb.ps1`. It builds **`usb_x_y_z\<app-folder>\`** with only:
   - git-tracked files
   - `wheels\`
   - `VERSION.txt`

   and places `DEPLOY-NOTES.md` next to the app folder. It refuses to run when the `DEPLOY-NOTES` section is missing or `wheels\` contains non-wheel files. It warns about uncommitted changes. It never includes `.env`, `.venv`, logs, certificates, caches or local data. Earlier `usb_*` folders are kept.

## 7. Install and update (on the server)

- First install: copy the app folder, run `scripts\2-install-offline.ps1`, fill in the secrets in `.env`, and start the app.
- Update: stop the app, rename the folder to `<app>-prev`, and copy in the new folder. Copy the server's own `.env` (and `certs\`) back from `<app>-prev`. Apply the `DEPLOY-NOTES` server settings for every version newer than `<app>-prev\VERSION.txt`, oldest first. Then run `2-install-offline.ps1`, start the app, and check `/api/health` and `VERSION.txt`.
- Rollback: swap the folders back. Keep only one previous version on the server. Any version can be rebuilt from its git tag.

## 8. Standard project files

```
<app package>/__init__.py   __version__ = "x.y.z"
.env.example               every key, safe defaults, PRODUCTION=False, no secrets
requirements.txt           top-level deps pinned ==
wheels/                    Windows x64 / cp311 wheels (built, not committed)
scripts/1-build-wheels.ps1     dev: build and verify wheels/
scripts/2-install-offline.ps1  server: venv + offline install + first-run .env
scripts/make-usb.ps1           dev: build usb_x_y_z/
scripts/run-server.bat         server: start the app
DEPLOY.md                  install, update and rollback on the server; prerequisites
DEPLOY-NOTES.md            per-version server settings (newest first)
static/vendor/             vendored frontend libraries
```

`.gitignore` must contain at least `.env`, `.venv/`, `wheels/`, `usb_*/`, `logs/` and `certs/`.

## 9. Security baseline

- HTTPS only in production, TLS 1.2 or later, HSTS, and certificate files readable only by Administrators and SYSTEM.
- Database access uses a least-privilege login (read-only unless writes are required) and parameterized queries only.
- The audit log holds metadata only: time, action, duration and outcome. It never holds content or personal data.
- There is no built-in login unless the project adds one. Document that the app must sit behind SSO, a reverse proxy, or a firewall rule.

## 10. What Claude must do in these projects

- Before adding any dependency, confirm a cp311 win_amd64 or pure-Python wheel exists, or that `pip wheel` can build one. Mention any new dependency in the reply.
- Never add CDN links, remote fonts, telemetry, or calls to public internet services in code that runs on the server.
- Any change that needs a new or changed `.env` key must also update `.env.example`, the config loader, and the next `DEPLOY-NOTES.md` section in the same change.
- Never put secrets in tracked files, and never copy the dev `.env` into a release.
- When asked to "make a release", follow §6 exactly and report the `usb_x_y_z` path, the wheel count, and the result of the offline-install check.
