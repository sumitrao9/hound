import importlib
import os

import pytest
from starlette.testclient import TestClient

from hound.mcp.metering import MeterStore


def make_app(tmp_path, monkeypatch, env=None):
    env = env or {}
    for k in ["HOUND_API_KEY", "HOUND_API_KEYS", "HOUND_ADMIN_KEY"]:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("HOUND_METER_DB", str(tmp_path / "meter.db"))
    # reload http to pick env? store passed directly
    from hound.mcp.http import create_app
    store = MeterStore(tmp_path / "meter.db")
    return create_app(store), store


def test_health_open(tmp_path, monkeypatch):
    app, _ = make_app(tmp_path, monkeypatch)
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.text == "ok"


def test_admin_requires_key(tmp_path, monkeypatch):
    app, _ = make_app(tmp_path, monkeypatch, {"HOUND_ADMIN_KEY": "admin"})
    with TestClient(app) as c:
        assert c.get("/admin/keys").status_code == 401
        r = c.post("/admin/keys", headers={"Authorization": "Bearer admin"}, json={"name": "t1", "rpm": 5, "daily": 10})
        assert r.status_code == 201
        key = r.json()["key"]
        assert key.startswith("hk_")


def test_x_api_key_and_quota(tmp_path, monkeypatch):
    app, store = make_app(tmp_path, monkeypatch, {"HOUND_ADMIN_KEY": "admin"})
    with TestClient(app) as c:
        key = c.post("/admin/keys", headers={"x-api-key": "admin"}, json={"name": "q", "rpm": 100, "daily": 1}).json()["key"]
        # /mcp GET is not a valid MCP call but guard runs; expect not 401
        r1 = c.get("/mcp", headers={"x-api-key": key})
        assert r1.status_code != 401
        r2 = c.get("/mcp", headers={"Authorization": f"Bearer {key}"})
        assert r2.status_code == 429


def test_revoke(tmp_path, monkeypatch):
    app, _ = make_app(tmp_path, monkeypatch, {"HOUND_ADMIN_KEY": "admin"})
    with TestClient(app) as c:
        key = c.post("/admin/keys", headers={"Authorization": "Bearer admin"}, json={"name": "r"}).json()["key"]
        c.post("/admin/keys/revoke", headers={"Authorization": "Bearer admin"}, json={"key": key})
        r = c.get("/mcp", headers={"Authorization": f"Bearer {key}"})
        assert r.status_code == 401
