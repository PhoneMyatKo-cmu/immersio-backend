"""
System tests for api/v1/endpoints/vocab.py  (vocabulary lookup route)

Route:
  POST /vocab/   get_vocabulary

TestClient with get_db overridden; get_vocab_by_surface_form and
get_caption_translation mocked at the endpoint module.
"""

import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

try:
    from api.v1.endpoints import vocab as ep
    from db.base import get_db
except Exception as exc:
    pytest.skip(f"vocab endpoint unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.system, pytest.mark.word_lookup]


def _client():
    app = FastAPI()
    app.include_router(ep.router)

    def _get_db():
        yield object()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _vocab():
    return types.SimpleNamespace(
        id=1, japanese_form="食べる", reading="taberu",
        meanings=[{"pos": "verb", "meanings": ["to eat"]}], estimated_level="N5",
    )


_REQ = {
    "vocab_surface_form": "食べる",
    "video_id": 1,
    "caption": {"id": 1, "text": "毎日ご飯を食べる。"},
}


def test_get_vocabulary_success(monkeypatch):
    monkeypatch.setattr(ep, "get_vocab_by_surface_form", lambda sf, db: _vocab())
    monkeypatch.setattr(ep, "get_caption_translation", lambda cap, db: "I eat rice every day.")
    r = _client().post("/vocab/", json=_REQ)
    assert r.status_code == 200
    body = r.json()
    assert body["vocab_id"] == 1
    assert body["surface_form"] == "食べる"
    assert body["sentence_translation"] == "I eat rice every day."
    assert body["context_sentence"] == {"id": 1, "text": "毎日ご飯を食べる。"}


def test_get_vocabulary_empty_surface_returns_400(monkeypatch):
    monkeypatch.setattr(ep, "get_vocab_by_surface_form", lambda sf, db: _vocab())
    monkeypatch.setattr(ep, "get_caption_translation", lambda cap, db: "x")
    req = dict(_REQ, vocab_surface_form="")
    r = _client().post("/vocab/", json=req)
    assert r.status_code == 400


def test_get_vocabulary_not_found_returns_404(monkeypatch):
    monkeypatch.setattr(ep, "get_vocab_by_surface_form", lambda sf, db: None)
    r = _client().post("/vocab/", json=_REQ)
    assert r.status_code == 404
    assert r.json()["detail"] == "Meaning Not Found."
