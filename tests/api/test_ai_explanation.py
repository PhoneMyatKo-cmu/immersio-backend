"""
System tests for api/v1/endpoints/ai_explanation.py

Route:
  POST /context-explanation/   get_ai_explanation   (authenticated)

TestClient with get_db / get_current_user overridden;
get_context_explanation_from_ai mocked at the endpoint module.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

try:
    from api.v1.endpoints import ai_explanation as ep
    from db.base import get_db
    from services.auth.authentication_service import get_current_user
    from services.ai_explanation_cache.ai_explanation_cache_service import (
        ServiceUnavailableError,
    )
    from schemas.vocab_context import ContextResponse
except Exception as exc:
    pytest.skip(f"ai_explanation endpoint unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.system, pytest.mark.word_lookup]


class _StubUser:
    id = 1
    email = "test@example.com"


def _client(current_user=_StubUser()):
    app = FastAPI()
    app.include_router(ep.router)

    def _get_db():
        yield object()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app)


_REQ = {
    "vocab_id": 1,
    "caption_id": 1,
    "surface_form": "食べる",
    "pos": ["verb"],
    "meanings": ["to eat"],
    "context_caption": "毎日ご飯を食べる。",
}


def _response():
    return ContextResponse(
        explanation="Plain dictionary form used in a casual statement of habit.",
        examples=[{"japanese": "毎朝パンを食べる。", "reading": "...", "english": "I eat bread every morning."}],
        confidence="high",
        dictionary_mismatche_detected=False,
    )


def test_get_ai_explanation_success(monkeypatch):
    monkeypatch.setattr(ep, "get_context_explanation_from_ai", lambda req, db: _response())
    r = _client().post("/context-explanation/", json=_REQ)
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] == "high"
    assert body["explanation"].startswith("Plain dictionary form")


def test_get_ai_explanation_service_unavailable_returns_503(monkeypatch):
    def boom(req, db):
        raise ServiceUnavailableError("Service is currently not available.")
    monkeypatch.setattr(ep, "get_context_explanation_from_ai", boom)
    r = _client().post("/context-explanation/", json=_REQ)
    assert r.status_code == 503


def test_get_ai_explanation_unauthenticated_returns_401(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(ep, "get_context_explanation_from_ai",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    r = _client(current_user=None).post("/context-explanation/", json=_REQ)
    assert r.status_code == 401
    assert called["n"] == 0


def test_get_ai_explanation_invalid_body_returns_422():
    r = _client().post("/context-explanation/", json={"vocab_id": 1})  # missing fields
    assert r.status_code == 422
