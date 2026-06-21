"""
Tests for services/video/video_validation_service.py  (Video Submission — Service)

validate_video orchestrates: extract_video_id -> fetch_video_metadata ->
fetch_caption_tracks -> check_video_japanese_suitability, and maps each failure
to a result dict with an `error` string (never raises for ordinary input).

[unit] The external YouTube calls (fetch_video_metadata, fetch_caption_tracks)
are mocked at this module's path; the pure utils (extract_video_id,
check_video_japanese_suitability) run for real. No network, no DB.

Importing the service pulls in youtube_api_service (yt-dlp etc.); the module
skips if those deps are unavailable.
"""

from unittest.mock import MagicMock

import pytest

try:
    from services.video import video_validation_service as svc
    from services.video.video_validation_service import validate_video
except Exception as exc:  # heavy external deps (yt-dlp, etc.) not installed
    pytest.skip(f"video_validation_service unavailable: {exc}", allow_module_level=True)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.video_submission,
    pytest.mark.video_validation,
]

VALID_URL = "https://youtu.be/dQw4w9WgXcQ"
VIDEO_ID = "dQw4w9WgXcQ"

META_JA = {"default_language": "ja", "default_audio_language": "ja", "title": "テスト"}
TRACK_JA = [{"snippet": {"language": "ja", "trackKind": "standard"}}]
TRACK_EN = [{"snippet": {"language": "en", "trackKind": "standard"}}]


def _set_externals(monkeypatch, metadata, tracks=None):
    """Patch the two external calls at the service module's namespace."""
    meta_mock = MagicMock(
        side_effect=metadata if isinstance(metadata, Exception) else None,
        return_value=None if isinstance(metadata, Exception) else metadata,
    )
    tracks_mock = MagicMock(return_value=tracks or [])
    monkeypatch.setattr(svc, "fetch_video_metadata", meta_mock)
    monkeypatch.setattr(svc, "fetch_caption_tracks", tracks_mock)
    return meta_mock, tracks_mock


def test_valid_japanese_video_returns_valid_result(monkeypatch):
    _set_externals(monkeypatch, META_JA, TRACK_JA)
    result = validate_video(VALID_URL)
    assert result["valid"] is True
    assert result["video_id"] == VIDEO_ID
    assert result["error"] is None
    assert result["meta_data"] == META_JA
    assert result["suitablity"]["is_suitable"] is True


def test_unparseable_url_rejected_without_calling_api(monkeypatch):
    meta_mock, _ = _set_externals(monkeypatch, META_JA, TRACK_JA)
    result = validate_video("https://example.com/not-a-video")
    assert result["valid"] is False
    assert result["error"] == "Invalid Youtube URL format"
    assert result["video_id"] is None
    meta_mock.assert_not_called()  # short-circuits before any API call


def test_metadata_api_error_reported(monkeypatch):
    _set_externals(monkeypatch, Exception("YouTube API down"))
    result = validate_video(VALID_URL)
    assert result["valid"] is False
    assert result["error"] == "Error on Youtube API"
    assert result["meta_data"] is None


def test_unavailable_video_when_metadata_empty(monkeypatch):
    _set_externals(monkeypatch, None)  # private / unavailable -> metadata None
    result = validate_video(VALID_URL)
    assert result["valid"] is False
    assert result["error"] == "Video Unavailable."


def test_not_suitable_carries_suitability_reason(monkeypatch):
    # Japanese audio metadata but no Japanese caption track -> not suitable.
    _set_externals(monkeypatch, META_JA, TRACK_EN)
    result = validate_video(VALID_URL)
    assert result["valid"] is False
    assert result["error"] == "No Japanese Captions for this video."
    assert result["suitablity"]["is_suitable"] is False
