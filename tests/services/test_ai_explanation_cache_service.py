"""
Tests for services/ai_explanation_cache/ai_explanation_cache_service.py (Word Look Up)

Covers docs/test_plan.md §7.1 (CEAI):
  CEAI-01 cache hit           -> cached response returned, Gemini not called   [unit]
  CEAI-02 cache miss          -> Gemini called, result cached and returned     [unit]
  CEAI-03 Gemini failure      -> ServiceUnavailableError, nothing cached        [unit]
  CEAI-04 cache-write failure -> database error propagates                      [unit]
  CEAI-05 cache key           -> keyed on the (vocab_id, caption_id) pair        [integration]

CEAI-01..04 mock check_cache / cache_explanation / Gemini (orchestration, no DB).
CEAI-05 exercises check_cache against the real DB. Module skips if the import
chain (Gemini client, etc.) is unavailable.
"""

import types
from unittest.mock import MagicMock

import pytest

try:
    from schemas.vocab_context import (
        ContextRequest,
        ExampleSentence,
        WordExplanationResponse,
    )
    from services.ai_explanation_cache import ai_explanation_cache_service as svc
    from services.ai_explanation_cache.ai_explanation_cache_service import (
        ServiceUnavailableError,
        get_context_explanation_from_ai,
    )
except Exception as exc:
    pytest.skip(
        f"ai_explanation_cache_service unavailable: {exc}", allow_module_level=True
    )

pytestmark = [pytest.mark.word_lookup]


def _request(vocab_id=1, caption_id=1):
    return ContextRequest(
        vocab_id=vocab_id,
        caption_id=caption_id,
        surface_form="食べる",
        pos=["verb"],
        meanings=["to eat"],
        context_caption="毎日ご飯を食べる。",
    )


def _gemini_response():
    return WordExplanationResponse(
        explanation="Plain dictionary form, used in a casual statement of habit.",
        examples=[
            ExampleSentence(
                japanese="毎朝パンを食べる。",
                reading="まいあさパンをたべる。",
                english="I eat bread every morning.",
            ),
            ExampleSentence(
                japanese="一緒に食べよう。",
                reading="いっしょにたべよう。",
                english="Let's eat together.",
            ),
        ],
        confidence="high",
        dictionary_mismatch_detected=False,
    )


# --- CEAI-01 ----------------------------------------------------------------
@pytest.mark.unit
def test_cache_hit_returns_cached_without_calling_gemini(monkeypatch):
    cached = types.SimpleNamespace(
        explanation="cached explanation",
        examples=[{"japanese": "x", "reading": "y", "english": "z"}],
        confidence_level="high",
        dictionary_mismatch_detected=False,
    )
    monkeypatch.setattr(svc, "check_cache", MagicMock(return_value=cached))
    gemini = MagicMock()
    monkeypatch.setattr(svc, "get_context_explanation_from_gemini", gemini)

    resp = get_context_explanation_from_ai(_request(), MagicMock())

    assert resp.explanation == "cached explanation"
    assert resp.confidence == "high"
    gemini.assert_not_called()


# --- CEAI-02 ----------------------------------------------------------------
@pytest.mark.unit
def test_cache_miss_calls_gemini_and_caches(monkeypatch):
    monkeypatch.setattr(svc, "check_cache", MagicMock(return_value=None))
    gemini = MagicMock(return_value=_gemini_response())
    monkeypatch.setattr(svc, "get_context_explanation_from_gemini", gemini)
    cache = MagicMock()
    monkeypatch.setattr(svc, "cache_explanation", cache)

    resp = get_context_explanation_from_ai(_request(), MagicMock())

    gemini.assert_called_once()
    cache.assert_called_once()
    assert resp.explanation.startswith("Plain dictionary form")
    assert len(resp.examples) == 2 and isinstance(resp.examples[0], dict)


# --- CEAI-03 ----------------------------------------------------------------
@pytest.mark.unit
def test_gemini_failure_raises_service_unavailable(monkeypatch):
    monkeypatch.setattr(svc, "check_cache", MagicMock(return_value=None))
    monkeypatch.setattr(
        svc,
        "get_context_explanation_from_gemini",
        MagicMock(side_effect=RuntimeError("gemini boom")),
    )
    cache = MagicMock()
    monkeypatch.setattr(svc, "cache_explanation", cache)

    with pytest.raises(ServiceUnavailableError):
        get_context_explanation_from_ai(_request(), MagicMock())
    cache.assert_not_called()


# --- CEAI-04 ----------------------------------------------------------------
@pytest.mark.unit
def test_cache_write_failure_propagates(monkeypatch):
    monkeypatch.setattr(svc, "check_cache", MagicMock(return_value=None))
    monkeypatch.setattr(
        svc,
        "get_context_explanation_from_gemini",
        MagicMock(return_value=_gemini_response()),
    )
    monkeypatch.setattr(
        svc, "cache_explanation", MagicMock(side_effect=Exception("db boom"))
    )

    with pytest.raises(Exception) as ei:
        get_context_explanation_from_ai(_request(), MagicMock())
    assert "db boom" in str(ei.value)


# --- CEAI-05 ----------------------------------------------------------------//Not Necessary
@pytest.mark.integration
def test_cache_key_is_vocab_caption_pair(db_session):
    from models.ai_explanation_cache import ConfidenceLevel, ContextualExplanation
    from models.processed_caption import Caption
    from models.video import Video
    from models.vocab import EstimatedLevel, Vocabulary
    from services.ai_explanation_cache.ai_explanation_cache_service import check_cache

    vocab = Vocabulary(
        japanese_form="食べる",
        reading="taberu",
        meanings=[{"pos": "verb", "meanings": ["to eat"]}],
        estimated_level=EstimatedLevel.N5,
    )
    video = Video(
        youtube_video_id="vid12345678",
        title="T",
        thumbnail_url="u",
        channel_name="C",
        duration_seconds=10,
    )
    db_session.add_all([vocab, video])
    db_session.commit()
    caption = Caption(
        video_id=video.id,
        caption_index=0,
        text="毎日ご飯を食べる。",
        tokens=[],
        start_time=0.0,
        end_time=1.0,
        duration=1.0,
    )
    db_session.add(caption)
    db_session.commit()
    db_session.add(
        ContextualExplanation(
            vocab_id=vocab.id,
            caption_id=caption.id,
            explanation="x",
            examples=[{"japanese": "a", "reading": "b", "english": "c"}],
            confidence_level=ConfidenceLevel.high,
            dictionary_mismatch_detected=False,
        )
    )
    db_session.commit()

    assert check_cache(vocab.id, caption.id, db_session) is not None
    assert check_cache(vocab.id, caption.id + 999, db_session) is None
