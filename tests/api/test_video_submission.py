"""
System tests for api/v1/endpoints/video_submission.py

Route:
  POST /submit-video/   add_video   (authenticated)

TestClient with get_db / get_current_user overridden and
submit_video_for_processing mocked at the endpoint module.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

try:
    from api.v1.endpoints import video_submission as ep
    from db.base import get_db
    from services.auth.authentication_service import get_current_user
    from services.video.video_submission_service import SubmissionResult
except Exception as exc:
    pytest.skip(f"video_submission endpoint unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.system, pytest.mark.video_submission]


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


def test_add_video_success(monkeypatch):
    calls = {}

    def fake_submit(url, db, background_tasks):
        calls["url"] = url
        return SubmissionResult(message="Successful", video_id=1, video_title="日本語レッスン")

    monkeypatch.setattr(ep, "submit_video_for_processing", fake_submit)
    r = _client().post("/submit-video/", json={"youtube_url": "https://youtu.be/dQw4w9WgXcQ"})
    assert r.status_code == 200
    assert r.json() == {"message": "Successful", "video_id": 1, "video_title": "日本語レッスン"}
    assert calls["url"] == "https://youtu.be/dQw4w9WgXcQ"


def test_add_video_unauthenticated_returns_401(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(
        ep, "submit_video_for_processing",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1),
    )
    r = _client(current_user=None).post(
        "/submit-video/", json={"youtube_url": "https://youtu.be/dQw4w9WgXcQ"}
    )
    assert r.status_code == 401
    assert called["n"] == 0  # service never invoked


def test_add_video_invalid_body_returns_422():
    r = _client().post("/submit-video/", json={})  # missing youtube_url
    assert r.status_code == 422
