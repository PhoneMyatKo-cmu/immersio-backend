"""
Tests for services/video/video_validation_service.py
Covers: docs/test_plan.md §5.1 (VV — validate_video). [unit; external API mocked]

Patch fetch_video_metadata / fetch_caption_tracks at this module's path:
    services.video.video_validation_service.fetch_video_metadata
"""

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.video_submission]


@pytest.mark.skip(reason="TODO VV-02: unparseable URL -> Invalid Youtube URL format, no API call")
def test_vv_02_bad_url():
    from services.video.video_validation_service import validate_video
    r = validate_video("https://example.com/x")
    assert r["valid"] is False
    assert r["error"] == "Invalid Youtube URL format"


@pytest.mark.skip(reason="TODO VV-01/03/04/05 (valid, API error, unavailable, not suitable)")
def test_vv_remaining():
    ...
