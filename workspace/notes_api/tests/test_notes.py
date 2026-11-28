from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_get_notes():
    # Create a note
    payload = {"id": 1, "content": "Hello OpenJarvis"}
    create_res = client.post("/notes", json=payload)
    assert create_res.status_code == 200
    assert create_res.json() == payload

    # Get notes
    get_res = client.get("/notes")
    assert get_res.status_code == 200
    assert len(get_res.json()) == 1
    assert get_res.json()[0]["content"] == "Hello OpenJarvis"
