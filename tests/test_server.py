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


# --------------------------------------------------------------------------- review actions


@pytest.fixture
def reviewed(client: TestClient) -> TestClient:
    """A client with the five sample leads already processed."""
    client.post("/run", json={"source": "sample"})
    return client


def status_of(client: TestClient, lead_id: str) -> str:
    leads = client.get("/leads").json()["leads"]
    return next(lead["status"] for lead in leads if lead["lead"]["id"] == lead_id)


@pytest.mark.parametrize(
    ("action", "status"),
    [("approve", "approved"), ("reject", "rejected"), ("handover", "needs_human")],
)
def test_review_actions_change_only_the_status(reviewed, action: str, status: str) -> None:
    before = next(x for x in reviewed.get("/leads").json()["leads"] if x["lead"]["id"] == "S001")
    response = reviewed.post("/leads/S001/review", json={"action": action})
    assert response.status_code == 200
    body = response.json()
    assert body["sent"] is False  # approving never sends anything
    after = body["lead"]
    assert after["status"] == status and after["reviewed_at"]
    assert after["draft_reply"] == before["draft_reply"] and after["score"] == before["score"]
    assert after["route"] == before["route"]
    assert status_of(reviewed, "S001") == status  # stored
    assert len(reviewed.get("/leads").json()["leads"]) == 5  # nothing duplicated


def test_handover_from_the_dashboard_records_a_reason(reviewed) -> None:
    lead = reviewed.post("/leads/S002/review", json={"action": "handover"}).json()["lead"]
    assert lead["handover_reason"] == "Taken over by a human in the dashboard"
    # an existing reason is kept
    kept = reviewed.post("/leads/S004/review", json={"action": "handover"}).json()["lead"]
    assert kept["handover_reason"].startswith("complaint")


def test_review_errors(reviewed) -> None:
    assert reviewed.post("/leads/NOPE/review", json={"action": "approve"}).status_code == 404
    # S004 is a complaint: it has no draft, so there is nothing to approve
    no_draft = reviewed.post("/leads/S004/review", json={"action": "approve"})
    assert no_draft.status_code == 409 and "no draft" in no_draft.json()["detail"]
    assert reviewed.post("/leads/S001/review", json={"action": "send"}).status_code == 422
    assert reviewed.post("/leads/S001/review", json={}).status_code == 422


def test_no_endpoint_can_send_anything(client: TestClient) -> None:
    paths = {route.path for route in client.app.routes}
    assert not any(word in path for path in paths for word in ("send", "email", "sms", "deliver"))


def test_review_is_allowed_by_cors_preflight(client: TestClient) -> None:
    response = client.options(
        "/leads/S001/review",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_server_binds_to_localhost_by_default() -> None:
    assert Settings.from_env({}).api_host == "127.0.0.1"
