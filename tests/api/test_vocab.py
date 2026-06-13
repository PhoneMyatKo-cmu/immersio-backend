"""
Tests for api/v1/endpoints/vocab.py
Covers: docs/test_plan.md
  §8.1 WL-01..06  POST /vocab/             (lookup)
  §8.2 SW-01..06  POST /vocab/save, GET /vocab/check-duplicate
[integration — TestClient via the `client` fixture]
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.word_lookup]


@pytest.mark.skip(reason="TODO WL-03/04: empty surface -> 400, not found -> 404")
def test_wl_validation(client):
    ...


@pytest.mark.skip(reason="TODO WL-01/02/06: lookup happy paths + translate fallback")
def test_wl_lookup(client):
    ...


@pytest.mark.skip(reason="TODO SW-01..06: save, 401, duplicate 500, check-duplicate scoping")
def test_sw_save_and_check(client, fx_user_save):
    ...
