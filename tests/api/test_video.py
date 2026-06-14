"""
Tests for api/v1/endpoints/video.py
Covers: docs/test_plan.md §6.2 (RD-01..04):
  GET /video/{id}, GET /video/{id}/shadowing-status.
[integration — TestClient via the `client` fixture]
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints import video as video_endpoint
from db.base import get_db

pytestmark = [pytest.mark.integration, pytest.mark.video_submission]


@pytest.fixture()
def video_client():
    app = FastAPI()
    db = object()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.include_router(video_endpoint.router)

    with TestClient(app) as client:
        yield client, db


def test_get_home_feed_uses_default_query_params(monkeypatch, video_client):
    client, db = video_client
    videos = [
        {
            "youtube_video_id": "abc123",
            "title": "Nihongo Basics",
            "thumbnail_url": "https://example.com/thumb.jpg",
            "channel_name": "Immersio",
            "duration_seconds": 180,
        }
    ]
    calls = []

    def fake_get_videos(*args, **kwargs):
        calls.append((args, kwargs))
        return videos, 7

    monkeypatch.setattr(video_endpoint, "get_videos", fake_get_videos)

    response = client.get("/video/")

    assert response.status_code == 200
    assert response.json() == [videos, 2]
    assert calls == [((db,), {"search": None, "page": 1, "page_size": 6})]


def test_get_home_feed_lowercases_search_and_uses_pagination(
    monkeypatch, video_client
):
    client, db = video_client
    videos = [
        {
            "youtube_video_id": "xyz789",
            "title": "Japanese Listening",
            "thumbnail_url": "https://example.com/listening.jpg",
            "channel_name": "Study Channel",
            "duration_seconds": 240,
        }
    ]
    calls = []

    def fake_get_videos(*args, **kwargs):
        calls.append((args, kwargs))
        return videos, 13

    monkeypatch.setattr(video_endpoint, "get_videos", fake_get_videos)

    response = client.get("/video/?search=NiHoNgO&page=2&page_size=5")

    assert response.status_code == 200
    assert response.json() == [videos, 3]
    assert calls == [((db,), {"search": "nihongo", "page": 2, "page_size": 5})]


def test_get_home_feed_returns_zero_pages_for_empty_result(
    monkeypatch, video_client
):
    client, db = video_client
    calls = []

    def fake_get_videos(*args, **kwargs):
        calls.append((args, kwargs))
        return [], 0

    monkeypatch.setattr(video_endpoint, "get_videos", fake_get_videos)

    response = client.get("/video/?page_size=10")

    assert response.status_code == 200
    assert response.json() == [[], 0]
    assert calls == [((db,), {"search": None, "page": 1, "page_size": 10})]


@pytest.mark.skip(reason="TODO RD-01/02: get_video 200 / 404")
def test_rd_get_video(client):
    ...


@pytest.mark.skip(reason="TODO RD-03/04: shadowing-status 200 / 404")
def test_rd_shadowing_status(client):
    ...
