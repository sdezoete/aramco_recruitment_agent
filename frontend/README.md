# Frontend (Development)

## What is included

- `index.html`: three-panel recruiter workspace shell.
- `styles.css`: responsive visual system and layout.
- `app.js`: tab behavior + API integration for requisitions, applications, ingest, clarification, and candidate details.

## Run locally

1. Start API server from repository root:

```powershell
C:/Users/HRSCE-3/Documents/vs_projects/aramco_recruitment_agent/.venv/Scripts/python.exe run_api.py
```

2. In a second terminal, serve the frontend directory:

```powershell
cd frontend
C:/Users/HRSCE-3/Documents/vs_projects/aramco_recruitment_agent/.venv/Scripts/python.exe -m http.server 5500
```

3. Open in browser:

- `http://127.0.0.1:5500`

## Notes

- Frontend API base is `http://127.0.0.1:8000` in `app.js`.
- CORS is enabled for local frontend dev origins in `app/api/main.py`.
