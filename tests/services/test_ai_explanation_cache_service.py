"""
Tests for services/ai_explanation_cache/ai_explanation_cache_service.py
Covers: docs/test_plan.md §7.1 (CEAI-01..05 — get_context_explanation_from_ai).
[integration — DB-backed cache; mock get_context_explanation_from_gemini at this
module's path]
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.word_lookup]


@pytest.mark.skip(reason="TODO CEAI-01: cache hit returns cached response, Gemini not called")
def test_ceai_01_cache_hit(db_session, fx_context_request):
    ...


@pytest.mark.skip(reason="TODO CEAI-02/03/05: miss->Gemini->cache, failure->503, key specificity")
def test_ceai_miss_and_failure(db_session, fx_context_request):
    ...
