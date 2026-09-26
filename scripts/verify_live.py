import sys
from pathlib import Path

# Add backend directory to sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_path))

import threading
import time
import httpx
import uvicorn
from app.main import app

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")

def verify():
    # Start server in background thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1.5)  # Wait for server startup

    base_url = "http://127.0.0.1:8001"
    with httpx.Client(base_url=base_url) as client:
        # 1. Verify Health
        health_res = client.get("/api/v1/health")
        print("GET /api/v1/health status:", health_res.status_code)
        print("GET /api/v1/health body:", health_res.json())
        assert health_res.status_code == 200
        assert health_res.json()["status"] == "ok"

        # 2. Verify Readiness
        readiness_res = client.get("/api/v1/readiness")
        print("GET /api/v1/readiness status:", readiness_res.status_code)
        print("GET /api/v1/readiness body:", readiness_res.json())
        # Since Postgres container isn't running on localhost:5432 yet, it correctly reports not_ready with 503
        assert readiness_res.status_code in {200, 503}

        # 3. Verify OpenAPI documentation
        docs_res = client.get("/docs")
        print("GET /docs status:", docs_res.status_code)
        assert docs_res.status_code == 200

        openapi_res = client.get("/openapi.json")
        print("GET /openapi.json status:", openapi_res.status_code)
        assert openapi_res.status_code == 200

    print("ALL LIVE ENDPOINT VERIFICATIONS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    verify()
