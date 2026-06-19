"""
System tests for api/v1/endpoints/vocab.py  (user-vocabulary routes)

Routes:
  POST /vocab/save            save_vocab_for_user          (authenticated)
  GET  /vocab/check-duplicate check_duplicate_vocab_per_user (authenticated)

TestClient with get_db / get_current_user overridden; save_vocab_to_library
and check_duplicate_vocab mocked at the endpoint module.
"""

import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

try:
    from api.v1.endpoints import vocab as ep
    from db.base import get_db
    from services.auth.authentication_service import get_current_user
except Exception as exc:
    pytest.skip(f"vocab endpoint unavailable: {exc}", allow_module_level=True)

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


_SAVE = {"vocab_id": 1, "video_id": 1, "caption_id": 1, "timestamp": 12.5}


def test_save_vocab_success(monkeypatch):
    calls = {}
    monkeypatch.setattr(ep, "save_vocab_to_library",
                        lambda save, uid, db: calls.update(uid=uid))
    r = _client().post("/vocab/save", json=_SAVE)
    assert r.status_code == 200
    assert r.json() == {"message": "success"}
    assert calls["uid"] == 1


def test_save_vocab_duplicate_returns_409(monkeypatch):
    def boom(save, uid, db):
        raise IntegrityError("INSERT", {}, Exception("uq_user_vocab"))
    monkeypatch.setattr(ep, "save_vocab_to_library", boom)
    r = _client().post("/vocab/save", json=_SAVE)
    assert r.status_code == 409
    assert r.json()["detail"] == "Vocab already saved"


def test_save_vocab_unexpected_error_returns_500(monkeypatch):
    def boom(save, uid, db):
        raise RuntimeError("db down")
    monkeypatch.setattr(ep, "save_vocab_to_library", boom)
    r = _client().post("/vocab/save", json=_SAVE)
    assert r.status_code == 500


def test_save_vocab_unauthenticated_returns_401(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(ep, "save_vocab_to_library",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    r = _client(current_user=None).post("/vocab/save", json=_SAVE)
    assert r.status_code == 401
    assert called["n"] == 0


def test_check_duplicate_true(monkeypatch):
    monkeypatch.setattr(ep, "check_duplicate_vocab",
                        lambda uid, vid, db: types.SimpleNamespace(id=7))
    r = _client().get("/vocab/check-duplicate?vocab_id=1")
    assert r.status_code == 200
    assert r.json() == {"saved": True}


def test_check_duplicate_false(monkeypatch):
    monkeypatch.setattr(ep, "check_duplicate_vocab", lambda uid, vid, db: None)
    r = _client().get("/vocab/check-duplicate?vocab_id=1")
    assert r.status_code == 200
    assert r.json() == {"saved": False}
