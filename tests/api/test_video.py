"""
System tests for api/v1/endpoints/video.py  (video read routes)

Routes:
  GET /video/                       get_home_feed
  GET /video/{id}                   get_video
  GET /video/{id}/shadowing-status  shadowing_status

Exercised through the FastAPI TestClient with get_db overridden and the
service layer (get_videos / get_video_by_id) mocked at the endpoint module.
"""

import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

try:
    from api.v1.endpoints import video as ep
    from db.base import get_db
except Exception as exc:  # external SDK / credential imports at module load
    pytest.skip(f"video endpoint unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.system, pytest.mark.video_submission]


def _client():
    app = FastAPI()
    app.include_router(ep.router)

    def _get_db():
        yield object()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _video_obj(**over):
    base = dict(
        youtube_video_id="dQw4w9WgXcQ",
        title="日本語レッスン",
        thumbnail_url="https://i.ytimg.com/vi/x/hqdefault.jpg",
        channel_name="Nihongo Channel",
        duration_seconds=180,
        is_shadowing_ready=False,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


def test_get_home_feed_returns_videos_and_total_pages(monkeypatch):
    monkeypatch.setattr(ep, "get_videos", lambda db, search, page, page_size: (["a", "b"], 12))
    r = _client().get("/video/")
    assert r.status_code == 200
    videos, total_pages = r.json()
    assert videos == ["a", "b"]
    assert total_pages == 2  # ceil(12 / 6)


def test_get_video_found_returns_video_response(monkeypatch):
    monkeypatch.setattr(ep, "get_video_by_id", lambda id, db: _video_obj())
    r = _client().get("/video/1")
    assert r.status_code == 200
    assert r.json() == {
        "youtube_video_id": "dQw4w9WgXcQ",
        "title": "日本語レッスン",
        "thumbnail_url": "https://i.ytimg.com/vi/x/hqdefault.jpg",
        "channel_name": "Nihongo Channel",
        "duration_seconds": 180,
    }


def test_get_video_not_found_returns_404(monkeypatch):
    monkeypatch.setattr(ep, "get_video_by_id", lambda id, db: None)
    r = _client().get("/video/999")
    assert r.status_code == 404
    assert r.json()["detail"] == "Video not found."


def test_shadowing_status_returns_flag(monkeypatch):
    monkeypatch.setattr(ep, "get_video_by_id", lambda id, db: _video_obj(is_shadowing_ready=True))
    r = _client().get("/video/1/shadowing-status")
    assert r.status_code == 200
    assert r.json() == {"is_shadowing_ready": True}


def test_shadowing_status_not_found_returns_404(monkeypatch):
    monkeypatch.setattr(ep, "get_video_by_id", lambda id, db: None)
    r = _client().get("/video/999/shadowing-status")
    assert r.status_code == 404
