"""
Tests for api/v1/endpoints/sentence.py
Covers: docs/test_plan.md §6.2 (RD-06 — GET /sentence/?video_id=).
[integration — TestClient via the `client` fixture]
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.video_submission]


@pytest.mark.skip(reason="TODO RD-06: sentence list returned; empty list when none")
def test_rd_06_get_sentences(client):
    ...
