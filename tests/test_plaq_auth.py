"""API-key resolution (auth-on-by-default, pytest stays open)."""

from __future__ import annotations

from plaq_api.auth import resolve_api_key


def test_pytest_does_not_require_auth_by_default(monkeypatch):
    monkeypatch.delenv("PLAQ_API_KEY", raising=False)
    monkeypatch.delenv("PLAQ_AUTH", raising=False)
    assert resolve_api_key(generate=False) is None


def test_env_key_wins(monkeypatch):
    monkeypatch.setenv("PLAQ_API_KEY", "secret-from-env")
    monkeypatch.delenv("PLAQ_AUTH", raising=False)
    assert resolve_api_key() == "secret-from-env"


def test_auth_off_flag(monkeypatch):
    monkeypatch.setenv("PLAQ_API_KEY", "secret-from-env")
    monkeypatch.setenv("PLAQ_AUTH", "off")
    assert resolve_api_key() is None


def test_is_authorized_bearer_and_cookie():
    from plaq_api.auth import is_authorized

    key = "plaq_secret"
    assert is_authorized(key, authorization="Bearer plaq_secret") is True
    assert is_authorized(key, cookie="plaq_secret") is True
    assert is_authorized(key, query_token="plaq_secret") is True
    assert is_authorized(key, authorization="Bearer nope") is False


def test_workbench_cookie_unlocks_api(monkeypatch, tmp_path):
    monkeypatch.setenv("PLAQ_API_KEY", "cookie-secret")
    from fastapi.testclient import TestClient
    from plaq_api.app import create_app
    from plaq_control_plane.db import DatabaseEngine
    from plaq_control_plane.repository import ControlPlaneRepository

    repo = ControlPlaneRepository(DatabaseEngine(str(tmp_path / "auth.db")))
    app = create_app(repository=repo)
    client = TestClient(app)
    assert client.get("/api/v1/tasks").status_code == 401
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/tasks", headers={"Authorization": "Bearer cookie-secret"}).status_code == 200
    client.cookies.set("plaq_session", "cookie-secret")
    assert client.get("/api/v1/tasks").status_code == 200
    repo.close()
