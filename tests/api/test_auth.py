"""
System tests for api/v1/endpoints/auth.py  (register, login, logout only)

Routes:
  POST /auth/register   register_user
  POST /auth/login      login_user
  POST /auth/logout     logout_user   (bearer token via oauth2_scheme)

TestClient with get_db overridden; the auth/user service functions
(hash_password, save_user, authenticate_user, create_token_pair, revoke_token)
mocked at the endpoint module so no DB or crypto work is required.
"""

import types
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

try:
    from api.v1.endpoints import auth as ep
    from db.base import get_db
    from models.user import EstimatedLevel, UserRole
except Exception as exc:
    pytest.skip(f"auth endpoint unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.system]


def _client():
    app = FastAPI()
    app.include_router(ep.router)

    def _get_db():
        yield object()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


# --- register -------------------------------------------------------------
def test_register_user_success(monkeypatch):
    monkeypatch.setattr(ep, "hash_password", lambda pw: f"hashed:{pw}")

    def fake_save_user(user, db):
        # the real save_user commits + refreshes, populating DB-side fields
        user.id = 1
        user.created_at = datetime(2026, 1, 1, 12, 0, 0)
        user.role = UserRole.LEARNER
        return user

    monkeypatch.setattr(ep, "save_user", fake_save_user)

    r = _client().post(
        "/auth/register",
        json={
            "first_name": "Test",
            "last_name": "Learner",
            "email": "New@Example.com",
            "password": "password123",
            "estimated_level": EstimatedLevel.beginner.value,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == 1
    assert body["email"] == "new@example.com"  # lower-cased by the endpoint
    assert "password" not in body and "password_hash" not in body


def test_register_invalid_body_returns_422():
    r = _client().post("/auth/register", json={"first_name": "x"})  # missing required
    assert r.status_code == 422


# --- login ----------------------------------------------------------------
def test_login_success(monkeypatch):
    monkeypatch.setattr(
        ep, "authenticate_user",
        lambda db, email, password: types.SimpleNamespace(email=email),
    )
    monkeypatch.setattr(
        ep, "create_token_pair",
        lambda email: {"access_token": "a.b.c", "refresh_token": "d.e.f", "token_type": "bearer"},
    )
    r = _client().post("/auth/login", json={"email": "user@example.com", "password": "password123"})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] == "a.b.c"
    assert body["refresh_token"] == "d.e.f"
    assert body["token_type"] == "bearer"


def test_login_bad_credentials_returns_401(monkeypatch):
    monkeypatch.setattr(ep, "authenticate_user", lambda db, email, password: None)
    r = _client().post("/auth/login", json={"email": "user@example.com", "password": "wrongpass"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect email or password"


# --- logout ---------------------------------------------------------------
def test_logout_success(monkeypatch):
    calls = []
    monkeypatch.setattr(ep, "revoke_token", lambda **kw: calls.append(kw["token"]))
    r = _client().post("/auth/logout", headers={"Authorization": "Bearer access.token.here"})
    assert r.status_code == 200
    assert r.json() == {"detail": "Logged out successfully"}
    assert "access.token.here" in calls


def test_logout_without_token_returns_401(monkeypatch):
    monkeypatch.setattr(ep, "revoke_token", lambda **kw: None)
    r = _client().post("/auth/logout")  # no Authorization header
    assert r.status_code == 401
