"""
Tests for services/video/video_submission_service.py
Covers: docs/test_plan.md §5.4 (SVP-01..15 — submit_video_for_processing).
[integration — orchestration; patch collaborators at this module's path and use a
real BackgroundTasks() to assert .tasks]

Patch targets (all under services.video.video_submission_service.*):
  validate_video, check_video_exists, fetch_raw_captions, save_video,
  get_video_by_youtube_video_id, save_tokenized_captions, save_vocabularies,
  save_sentence, change_shadowing_status, and the two background functions.
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.video_submission]


@pytest.mark.skip(reason="TODO SVP-11: is_standard branch — manual vs Whisper (key test)")
def test_svp_11_branch_decision():
    ...


@pytest.mark.skip(reason="TODO SVP-01/02/03 happy paths + dedup")
def test_svp_happy_and_dedup():
    ...


@pytest.mark.skip(reason="TODO SVP-04..10 error mapping (400/500), SVP-12..15 wiring/edge")
def test_svp_errors_and_wiring():
    ...
