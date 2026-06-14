"""
Tests for services/external/youtube_api_service.py  (Video Submission — External)

fetch_video_metadata is the one external wrapper with its own branching and
response-mapping logic. The service layer mocks this function away, so this is
the only place that logic is actually exercised.

Covers:
  YTM-01  200 + items        -> normalized metadata dict
  YTM-02  non-200 status     -> raises (Youtube Data API error)
  YTM-03  200 + no items     -> None (video does not exist)
  YTM-04  200 + private video -> None

[unit] httpx is mocked at the module path; no network call and no API key are
used. Module skips if its import chain (httpx / yt_dlp / requests) is missing.
"""

from unittest.mock import MagicMock

import pytest

try:
    from services.external import youtube_api_service as svc
    from services.external.youtube_api_service import fetch_video_metadata
except Exception as exc:
    pytest.skip(f"youtube_api_service unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.unit, pytest.mark.video_submission]


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _patch_httpx(monkeypatch, response):
    """Replace httpx.Client so .get(...) returns our canned response."""
    fake_client = MagicMock()
    fake_client.get.return_value = response
    monkeypatch.setattr(svc.httpx, "Client", lambda *a, **k: fake_client)


def _item(privacy="public"):
    return {
        "snippet": {
            "title": "Sample Video",
            "channelTitle": "Sample Channel",
            "thumbnails": {"high": {"url": "https://img/high.jpg"}},
            "defaultLanguage": "ja",
            "defaultAudioLanguage": "ja",
            "tags": ["japanese", "study"],
        },
        "contentDetails": {"duration": "PT3M30S"},
        "status": {"privacyStatus": privacy},
    }


# --- YTM-01 -----------------------------------------------------------------
def test_returns_normalized_metadata_for_existing_public_video(monkeypatch):
    _patch_httpx(monkeypatch, _FakeResponse(200, {"items": [_item()]}))

    result = fetch_video_metadata("dQw4w9WgXcQ")

    assert result == {
        "video_id": "dQw4w9WgXcQ",
        "title": "Sample Video",
        "channel_name": "Sample Channel",
        "thumbnail_url": "https://img/high.jpg",
        "duration_iso": "PT3M30S",
        "default_language": "ja",
        "default_audio_language": "ja",
        "tags": ["japanese", "study"],
        "duration": "PT3M30S",
    }


# --- YTM-02 -----------------------------------------------------------------
def test_raises_on_non_200_status(monkeypatch):
    _patch_httpx(monkeypatch, _FakeResponse(403, {}))

    with pytest.raises(Exception) as ei:
        fetch_video_metadata("dQw4w9WgXcQ")
    assert "403" in str(ei.value)


# --- YTM-03 -----------------------------------------------------------------
def test_returns_none_when_no_items(monkeypatch):
    _patch_httpx(monkeypatch, _FakeResponse(200, {"items": []}))

    assert fetch_video_metadata("invalidss000") is None


# --- YTM-04 -----------------------------------------------------------------
def test_returns_none_for_private_video(monkeypatch):
    _patch_httpx(monkeypatch, _FakeResponse(200, {"items": [_item(privacy="private")]}))

    assert fetch_video_metadata("dQw4w9WgXcQ") is None
