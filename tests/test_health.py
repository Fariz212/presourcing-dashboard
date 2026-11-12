import pytest

from app import create_app


@pytest.fixture()
def client():
    app = create_app({"TESTING": True})

    yield app.test_client()

    pool = app.extensions.get("khs_db_pool")
    if pool:
        pool.close()


def test_liveness(client):
    response = client.get("/health/live")

    assert response.status_code == 200

    data = response.get_json()
    assert data["status"] == "alive"
    assert data["service"] == "khs-monitoring"


def test_readiness(client):
    response = client.get("/health/ready")

    assert response.status_code == 200

    data = response.get_json()
    assert data["status"] == "ready"
    assert data["database"]["status"] == "connected"
    assert data["database"]["name"] == "khs_monitoring"


def test_root_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.get_json()["status"] == "running"
