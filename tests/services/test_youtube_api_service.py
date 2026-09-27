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


# --- YOUTUBE_PROXY / YOUTUBE_COOKIES ---------------------------------------


class _FakeYDL:
    """Captures the options download_audio passes to yt-dlp."""

    opts = None

    def __init__(self, opts):
        _FakeYDL.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download):
        return {
            "requested_downloads": [{"filepath": "/tmp/abc.wav"}],
        }


@pytest.mark.parametrize(
    ("proxy", "cookies", "expected"),
    [
        (None, None, {}),
        ("http://user:pass@proxy:8080", None, {"proxy": "http://user:pass@proxy:8080"}),
        (None, "/home/ubuntu/cookies.txt", {"cookiefile": "/home/ubuntu/cookies.txt"}),
    ],
)
def test_download_audio_passes_network_settings_only_when_set(
    monkeypatch, proxy, cookies, expected
):
    monkeypatch.setattr(svc, "YOUTUBE_PROXY", proxy)
    monkeypatch.setattr(svc, "YOUTUBE_COOKIES", cookies)
    monkeypatch.setattr(svc, "YoutubeDL", _FakeYDL)

    assert svc.download_audio("abc", "/tmp") == "/tmp/abc.wav"
    network = {k: v for k, v in _FakeYDL.opts.items() if k in ("proxy", "cookiefile")}
    assert network == expected


class _FakeSubsYDL:
    """Fake yt-dlp: reports available tracks, then writes the requested one."""

    info = {}
    write_file = True
    instance = None

    def __init__(self, opts):
        self.params = dict(opts)
        _FakeSubsYDL.instance = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download, process):
        assert download is False and process is False
        return _FakeSubsYDL.info

    def process_ie_result(self, info, download):
        if self.write_file:
            track = self.params["subtitleslangs"][0]
            path = self.params["outtmpl"].replace("%(id)s.%(ext)s", f"abc.{track}.json3")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"events": ["%s"]}' % track)


@pytest.mark.parametrize(
    ("info", "expected_track", "expected_auto"),
    [
        # Human subtitles win over auto captions.
        ({"subtitles": {"ja": []}, "automatic_captions": {"ja-orig": [], "ja": []}}, "ja", False),
        # Original-language ASR, not the machine-translated bare "ja".
        ({"subtitles": {}, "automatic_captions": {"ja-orig": [], "ja": []}}, "ja-orig", True),
        # Older metadata without -orig: fall back to bare "ja".
        ({"automatic_captions": {"ja": []}}, "ja", True),
    ],
)
def test_fetch_raw_captions_picks_best_track(monkeypatch, info, expected_track, expected_auto):
    monkeypatch.setattr(svc, "YOUTUBE_PROXY", None)
    monkeypatch.setattr(svc, "YOUTUBE_COOKIES", "/home/ubuntu/cookies.txt")
    monkeypatch.setattr(_FakeSubsYDL, "info", info)
    monkeypatch.setattr(_FakeSubsYDL, "write_file", True)
    monkeypatch.setattr(svc.yt_dlp, "YoutubeDL", _FakeSubsYDL)

    assert svc.fetch_raw_captions("abc") == {"events": [expected_track]}
    params = _FakeSubsYDL.instance.params
    assert params["cookiefile"] == "/home/ubuntu/cookies.txt"
    assert params["subtitleslangs"] == [expected_track]
    assert params["writeautomaticsub"] is expected_auto
    assert params["writesubtitles"] is (not expected_auto)


def test_fetch_raw_captions_raises_when_no_japanese_track(monkeypatch):
    monkeypatch.setattr(_FakeSubsYDL, "info", {"subtitles": {"en": []}, "automatic_captions": {"en-orig": []}})
    monkeypatch.setattr(svc.yt_dlp, "YoutubeDL", _FakeSubsYDL)

    with pytest.raises(RuntimeError, match="No ja captions available"):
        svc.fetch_raw_captions("abc")


def test_fetch_raw_captions_raises_when_file_not_written(monkeypatch):
    monkeypatch.setattr(_FakeSubsYDL, "info", {"subtitles": {"ja": []}})
    monkeypatch.setattr(_FakeSubsYDL, "write_file", False)
    monkeypatch.setattr(svc.yt_dlp, "YoutubeDL", _FakeSubsYDL)

    with pytest.raises(RuntimeError, match="No ja json3 captions"):
        svc.fetch_raw_captions("abc")


@pytest.mark.parametrize("fetch_pot", [True, False])
def test_fetch_raw_captions_forces_po_token_only_when_enabled(monkeypatch, fetch_pot):
    monkeypatch.setattr(svc, "YOUTUBE_FETCH_POT", fetch_pot)
    monkeypatch.setattr(_FakeSubsYDL, "info", {"subtitles": {"ja": []}})
    monkeypatch.setattr(_FakeSubsYDL, "write_file", True)
    monkeypatch.setattr(svc.yt_dlp, "YoutubeDL", _FakeSubsYDL)

    svc.fetch_raw_captions("abc")

    extractor_args = _FakeSubsYDL.instance.params.get("extractor_args")
    if fetch_pot:
        assert extractor_args == {"youtube": {"fetch_pot": ["always"]}}
    else:
        assert extractor_args is None
