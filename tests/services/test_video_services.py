"""
Tests for services/video/video_services.py
Covers: docs/test_plan.md §5.2 (DBS-01..04):
  save_video, check_video_exists, get_video_by_id / _by_youtube_video_id,
  change_shadowing_status.
[integration — uses the db_session fixture]
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.video_submission]


@pytest.mark.skip(reason="TODO DBS-01: save_video persists row + parses ISO duration to seconds")
def test_dbs_01_save_video(db_session, fx_meta_ja):
    from services.video.video_services import save_video
    ...


@pytest.mark.skip(reason="TODO DBS-02/03/04 (exists lookup, get-by-id, shadowing status)")
def test_dbs_video_queries(db_session):
    ...
