from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from leadgen.config import Settings
from leadgen.server import create_app
from leadgen.storage import LocalStorage


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(
        mock_llm=True, data_dir=str(tmp_path / "data"), cors_origins=("http://localhost:5173",)
    )
    return TestClient(create_app(settings))


def test_queue_run_and_read_back(client: TestClient, tmp_path) -> None:
    assert client.get("/leads").json() == {"leads": [], "pending": []}

    created = client.post(
        "/leads",
        json={"name": "Api Lead", "email": "api@example.com",
              "message": "Office in Gulberg Lahore, bill 120,000, need a site survey this month"},
    )  # fmt: skip
    assert created.status_code == 201 and created.json()["status"] == "queued"
    lead_id = created.json()["id"]
    assert [p["id"] for p in client.get("/leads").json()["pending"]] == [lead_id]

    result = client.post("/run", json={}).json()
    assert result["run"]["leads_processed"] == 1 and result["run"]["source"] == "webhook"
    assert result["leads"][0]["route"] == "draft_reply" and result["leads"][0]["is_hot"]

    listing = client.get("/leads").json()
    assert listing["pending"] == [] and listing["leads"][0]["status"] == "pending_approval"
    assert [run["id"] for run in client.get("/runs").json()["runs"]] == [result["run"]["id"]]
    assert len(LocalStorage(tmp_path / "data").list_records()) == 1


def test_dry_run_over_the_api_stores_nothing(client: TestClient) -> None:
    result = client.post("/run", json={"source": "sample", "dry_run": True, "limit": 2}).json()
    assert result["run"]["dry_run"] and len(result["leads"]) == 2
    assert client.get("/leads").json()["leads"] == [] and client.get("/runs").json()["runs"] == []


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/leads", {"name": "No message"}),
        ("/leads", {"message": ""}),
        ("/leads", {"message": "x" * 5001}),
        ("/run", {"source": "file"}),
        ("/run", {"limit": 0}),
    ],
)
def test_bad_requests_are_rejected(client: TestClient, path: str, body: dict) -> None:
    assert client.post(path, json=body).status_code == 422


def test_cors_comes_from_settings(client: TestClient) -> None:
    allowed = client.get("/leads", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    other = client.get("/leads", headers={"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in other.headers


def test_missing_key_gives_400_not_500(tmp_path) -> None:
    client = TestClient(create_app(Settings(data_dir=str(tmp_path))))
    response = client.post("/run", json={"source": "sample"})
    assert response.status_code == 400 and "OPENAI_API_KEY" in response.json()["detail"]


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok", "mode": "mock"}
