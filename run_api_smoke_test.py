from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.api.main import app


def main() -> None:
    client = TestClient(app)

    print("health:")
    print(client.get("/health").json())

    print("ats_requisitions:")
    reqs = client.get("/ats/requisitions").json()
    print(json.dumps(reqs, indent=2, ensure_ascii=True))

    print("ats_applications:")
    apps = client.get(f"/ats/requisitions/{reqs['job_requisitions'][0]['requisition_id']}/applications?limit=20").json()
    print(json.dumps({"count": apps.get("count")}, indent=2, ensure_ascii=True))

    print("requisition_ingest:")
    ingest = client.post(
        "/requisition/ingest",
        json={
            "title": "Machine Learning Engineer",
            "department": "AI",
            "location": "Dhahran",
            "jd_text": "Looking for a senior machine learning engineer with 5+ years, Python, MLOps, and Kubernetes. Bachelor degree required.",
        },
    ).json()
    print(json.dumps({"status": ingest.get("status"), "session_id": ingest.get("session_id")}, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
