"""
Tests for api/v1/endpoints/ai_explanation.py
Covers: docs/test_plan.md §8.3 (CE-01..04 — POST /context-explanation/).
Plus cross-cutting auth: §9 (XC-01..03) can live here or in a dedicated module.
[integration — TestClient via the `client` fixture]
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.word_lookup]


@pytest.mark.skip(reason="TODO CE-02: unauthenticated -> 401")
def test_ce_02_unauthenticated(client):
    ...


@pytest.mark.skip(reason="TODO CE-01/03/04: 200, 503 on ServiceUnavailableError, 422")
def test_ce_remaining(client, fx_context_request):
    ...
