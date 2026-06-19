"""
System tests for api/v1/endpoints/caption.py

Route:
  GET /caption/?video_id=   get_captions_by_video

TestClient with get_db overridden and get_captions_by_video_id mocked.
"""

import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

try:
    from api.v1.endpoints import caption as ep
    from db.base import get_db
except Exception as exc:
    pytest.skip(f"caption endpoint unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.system, pytest.mark.video_submission]


def _client():
    app = FastAPI()
    app.include_router(ep.router)

    def _get_db():
        yield object()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _caption(i):
    return types.SimpleNamespace(
        id=i, caption_index=i, text="私はご飯を食べる",
        tokens=[], start_time=0.0, end_time=2.0, duration=2.0,
    )


def test_get_captions_returns_list(monkeypatch):
    monkeypatch.setattr(ep, "get_captions_by_video_id", lambda video_id, db: [_caption(0), _caption(1)])
    r = _client().get("/caption/?video_id=1")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["caption_index"] == 0
    assert set(body[0]) == {"id", "caption_index", "text", "tokens", "start_time", "end_time", "duration"}


def test_get_captions_empty_when_none(monkeypatch):
    monkeypatch.setattr(ep, "get_captions_by_video_id", lambda video_id, db: [])
    r = _client().get("/caption/?video_id=999")
    assert r.status_code == 200
    assert r.json() == []


def test_get_captions_missing_video_id_returns_422():
    r = _client().get("/caption/")
    assert r.status_code == 422
