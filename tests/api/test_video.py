"""
Tests for api/v1/endpoints/video.py
Covers: docs/test_plan.md §6.2 (RD-01..04):
  GET /video/{id}, GET /video/{id}/shadowing-status.
[integration — TestClient via the `client` fixture]
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.video_submission]


@pytest.mark.skip(reason="TODO RD-01/02: get_video 200 / 404")
def test_rd_get_video(client):
    ...


@pytest.mark.skip(reason="TODO RD-03/04: shadowing-status 200 / 404")
def test_rd_shadowing_status(client):
    ...
