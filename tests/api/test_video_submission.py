"""
Tests for api/v1/endpoints/video_submission.py
Covers: docs/test_plan.md §6.1 (AV-01..04 — POST /submit-video/).
[integration — TestClient via the `client` fixture]
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.video_submission]


@pytest.mark.skip(reason="TODO AV-02: unauthenticated -> 401, service not called")
def test_av_02_unauthenticated(client):
    ...


@pytest.mark.skip(reason="TODO AV-01/03/04: success, 422 body, error propagation")
def test_av_remaining(client):
    ...
