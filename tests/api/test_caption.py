"""
Tests for api/v1/endpoints/caption.py
Covers: docs/test_plan.md §6.2 (RD-05 — GET /caption/?video_id=).
[integration — TestClient via the `client` fixture]
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.video_submission]


@pytest.mark.skip(reason="TODO RD-05: caption list returned; empty list when none")
def test_rd_05_get_captions(client):
    ...
