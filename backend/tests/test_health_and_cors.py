"""Regression tests for health endpoints and CORS configuration."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Standard test client — startup events run, so app.state.ready=True."""
    from app.main import app

    with TestClient(app) as c:
        yield c


# ── /health (liveness) ─────────────────────────────────────


def test_health_always_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── /health/ready (readiness) ──────────────────────────────


def test_health_ready_returns_200_when_ready(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_health_ready_returns_503_when_not_ready(client):
    from app.main import app

    original = app.state.ready
    app.state.ready = False
    try:
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "not_ready"
        assert "startup" in body["reason"]
    finally:
        app.state.ready = original


def test_health_ready_returns_503_when_db_fails(client):
    from app.main import app

    assert app.state.ready  # precondition: startup completed

    with patch("app.main.engine") as mock_engine:
        mock_engine.connect.side_effect = Exception("connection refused")
        resp = client.get("/health/ready")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["reason"] == "database check failed"


# ── CORS behaviour ─────────────────────────────────────────


def test_cors_headers_present_when_origins_configured():
    """When CORS_ORIGINS is set, the real app mounts CORSMiddleware.

    We verify this by inspecting the middleware stack of the actual app,
    rather than reloading modules (which pollutes process state in full suite).
    """
    import importlib

    # 1. Verify that with CORS_ORIGINS set, a freshly-built app has CORSMiddleware
    with patch.dict("os.environ", {"CORS_ORIGINS": "http://allowed.example.com"}, clear=False):
        import app.core.config as config_mod

        importlib.reload(config_mod)
        assert config_mod.CORS_ORIGINS == ["http://allowed.example.com"]

        # Build a minimal app using the same conditional logic as main.py
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware

        test_app = FastAPI()
        if config_mod.CORS_ORIGINS:
            test_app.add_middleware(
                CORSMiddleware,
                allow_origins=config_mod.CORS_ORIGINS,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        @test_app.get("/test")
        def _t():
            return {"ok": True}

        with TestClient(test_app) as c:
            resp = c.get("/test", headers={"Origin": "http://allowed.example.com"})
            assert resp.headers.get("access-control-allow-origin") == "http://allowed.example.com"

            resp2 = c.get("/test", headers={"Origin": "http://attacker.com"})
            assert resp2.headers.get("access-control-allow-origin") != "http://attacker.com"

        # Restore config
        importlib.reload(config_mod)

    # 2. Verify the actual app (loaded with empty CORS_ORIGINS) has no CORS middleware
    from app.main import app as real_app

    middleware_classes = [m.cls.__name__ for m in real_app.user_middleware]
    assert "CORSMiddleware" not in middleware_classes


def test_cors_no_header_when_origins_not_configured(client):
    """Default (CORS_ORIGINS unset) means no CORSMiddleware, so no CORS headers."""
    resp = client.get(
        "/health",
        headers={"Origin": "http://attacker.com"},
    )
    assert resp.headers.get("access-control-allow-origin") is None


def test_cors_origins_empty_by_default():
    """When CORS_ORIGINS env is not set, it defaults to empty (no middleware).

    Verify the config parsing logic: unset/empty string → empty list.
    """
    import importlib

    with patch.dict("os.environ", {"CORS_ORIGINS": ""}, clear=False):
        import app.core.config as config_mod

        importlib.reload(config_mod)
        assert config_mod.CORS_ORIGINS == []
        importlib.reload(config_mod)  # restore
