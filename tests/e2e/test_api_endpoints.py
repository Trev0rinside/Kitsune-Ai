"""Integration/E2E tests for the FastAPI service endpoints."""

import httpx
import pytest
from reverse_guardrail.api.app import app


@pytest.mark.asyncio
async def test_api_health():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_api_start_unauthorized_fails_killswitch():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "config": {
                "target": {
                    "authorized": False,
                    "engagement_id": "ENG-TEST",
                },
                "max_rounds": 2,
            }
        }
        resp = await client.post("/api/v1/pipeline/start", json=payload)
        assert resp.status_code == 403
        data = resp.json()
        assert "KILL-SWITCH" in data["detail"]


@pytest.mark.asyncio
async def test_api_start_and_status_authorized():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "config": {
                "target": {
                    "authorized": True,
                    "engagement_id": "ENG-API-TEST-2026",
                    "target_name": "API Mock Target",
                },
                "max_rounds": 2,
                "attempts_per_round": 2,
                "confidence_threshold": 0.80,
                "stagnation_patience_rounds": 2,
                "rate_limit_rps": 50.0,
            }
        }
        # Start pipeline
        resp = await client.post("/api/v1/pipeline/start", json=payload)
        assert resp.status_code == 200
        start_data = resp.json()
        run_id = start_data["run_id"]
        assert run_id.startswith("RUN-")
        assert start_data["status"] == "completed"

        # Check status endpoint
        status_resp = await client.get(f"/api/v1/pipeline/{run_id}/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["run_id"] == run_id
        assert status_data["total_fragments_count"] > 0

        # Check report endpoint
        report_resp = await client.get(f"/api/v1/pipeline/{run_id}/report")
        assert report_resp.status_code == 200
        report_data = report_resp.json()
        assert "reconstructed_prompt" in report_data

        # Check graph endpoint
        graph_resp = await client.get(f"/api/v1/pipeline/{run_id}/graph")
        assert graph_resp.status_code == 200
        graph_data = graph_resp.json()
        assert len(graph_data["nodes"]) > 0

        # Check fragments endpoint
        frags_resp = await client.get(f"/api/v1/pipeline/{run_id}/fragments")
        assert frags_resp.status_code == 200
        frags_data = frags_resp.json()
        assert len(frags_data) > 0

        # Check audit logs endpoint
        audit_resp = await client.get("/api/v1/audit/logs")
        assert audit_resp.status_code == 200
        audit_data = audit_resp.json()
        assert len(audit_data) > 0

        # Check vulnerabilities endpoint
        vuln_resp = await client.get(f"/api/v1/pipeline/{run_id}/vulnerabilities")
        assert vuln_resp.status_code == 200
        vuln_data = vuln_resp.json()
        assert "vulnerabilities" in vuln_data
        assert "delimiter_isolation_score" in vuln_data

        # Check hardening endpoint
        hard_resp = await client.get(f"/api/v1/pipeline/{run_id}/hardening")
        assert hard_resp.status_code == 200
        hard_data = hard_resp.json()
        assert "hardened_system_prompt" in hard_data
        assert "remediations" in hard_data
        assert "executive_summary" in hard_data


@pytest.mark.asyncio
async def test_frontend_serving():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "REVERSE-GUARDRAIL" in resp.text
        assert "styles.css" in resp.text

        css_resp = await client.get("/static/styles.css")
        assert css_resp.status_code == 200

        js_resp = await client.get("/static/app.js")
        assert js_resp.status_code == 200
