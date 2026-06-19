"""
System tests for api/v1/endpoints/sentence.py

Route:
  GET /sentence/?video_id=   get_sentences_by_video

TestClient with get_db overridden and get_sentence_by_video_id mocked.
"""

import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

try:
    from api.v1.endpoints import sentence as ep
    from db.base import get_db
except Exception as exc:
    pytest.skip(f"sentence endpoint unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.system, pytest.mark.video_submission]


def _client():
    app = FastAPI()
    app.include_router(ep.router)

    def _get_db():
        yield object()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _sentence(i):
    return types.SimpleNamespace(
        sentence_index=i, text="おはよう", start_time=0.0, end_time=1.2,
        duration=1.2, translation=None,
    )


def test_get_sentences_returns_list(monkeypatch):
    monkeypatch.setattr(ep, "get_sentence_by_video_id", lambda video_id, db: [_sentence(0), _sentence(1)])
    r = _client().get("/sentence/?video_id=1")
    assert r.status_code == 200
    body = r.json()
    assert [s["sentence_index"] for s in body] == [0, 1]
    assert body[0]["translation"] is None


def test_get_sentences_empty_when_none(monkeypatch):
    monkeypatch.setattr(ep, "get_sentence_by_video_id", lambda video_id, db: [])
    r = _client().get("/sentence/?video_id=999")
    assert r.status_code == 200
    assert r.json() == []


def test_get_sentences_missing_video_id_returns_422():
    r = _client().get("/sentence/")
    assert r.status_code == 422
