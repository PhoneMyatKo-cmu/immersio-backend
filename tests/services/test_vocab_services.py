"""
Tests for services/vocab/vocab_services.py  (Video Submission + Word Look Up)

Planned scope (docs/test_plan.md):
  §5.3 SVOC-01..03  save_vocabularies            [Video Submission]
  §7.3 VDS-01       get_vocab_by_surface_form     [Word Look Up]

[integration] Uses the real test DB via db_session. lookup_word_full is mocked at
the service path so save_vocabularies doesn't depend on JMdict / cutlet / Google
Translate — only the de-dup + persistence logic is under test. The module skips
if its import chain (dictionary_lookup_helpers -> fugashi/cutlet/GCT) is missing.
"""

import pytest

try:
    from sqlalchemy import select

    from models.vocab import EstimatedLevel, Vocabulary
    from services.vocab import vocab_services as svc
    from services.vocab.vocab_services import (
        get_vocab_by_id,
        get_vocab_by_surface_form,
        save_vocabularies,
    )
except Exception as exc:  # fugashi / cutlet / GCT key at import, etc.
    pytest.skip(f"vocab_services unavailable: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.integration]


def _fake_lookup(token):
    """Deterministic stand-in for lookup_word_full (no JMdict / translate)."""
    return {
        "found": True,
        "romanji_reading": "yomi",
        "meanings": [{"pos": "noun", "meanings": ["meaning"]}],
        "jlpt_tier": "N5",
    }


def _all_forms(db):
    return [v.japanese_form for v in db.scalars(select(Vocabulary)).all()]


# --- SVOC-01 ----------------------------------------------------------------
@pytest.mark.video_submission
def test_save_vocabularies_inserts_new_words(monkeypatch, db_session):
    monkeypatch.setattr(svc, "lookup_word_full", _fake_lookup)
    save_vocabularies([("猫", "猫", "猫"), ("犬", "犬", "犬")], db_session)
    forms = _all_forms(db_session)
    assert set(forms) == {"猫", "犬"}


# --- SVOC-02 ----------------------------------------------------------------
@pytest.mark.video_submission
def test_save_vocabularies_skips_existing_word(monkeypatch, db_session):
    db_session.add(
        Vocabulary(
            japanese_form="猫",
            reading="neko",
            meanings=[{"pos": "noun", "meanings": ["cat"]}],
            estimated_level=EstimatedLevel.N5,
            lemma="猫",
        )
    )
    db_session.commit()

    monkeypatch.setattr(svc, "lookup_word_full", _fake_lookup)
    save_vocabularies([("猫", "猫", "猫"), ("犬", "犬", "犬")], db_session)

    forms = _all_forms(db_session)
    assert forms.count("猫") == 1  # not duplicated
    assert "犬" in forms  # new one added


# --- SVOC-03 ----------------------------------------------------------------
@pytest.mark.video_submission
def test_save_vocabularies_dedups_within_input(monkeypatch, db_session):
    monkeypatch.setattr(svc, "lookup_word_full", _fake_lookup)
    save_vocabularies([("猫", "猫", "猫"), ("猫", "猫", "猫")], db_session)
    assert _all_forms(db_session).count("猫") == 1


# --- VDS-01 -----------------------------------------------------------------
@pytest.mark.word_lookup
def test_get_vocab_by_surface_form_returns_row_if_found(db_session):
    db_session.add(
        Vocabulary(
            japanese_form="食べる",
            reading="taberu",
            meanings=[{"pos": "verb", "meanings": ["to eat"]}],
            estimated_level=EstimatedLevel.N5,
            lemma="食べる",
        )
    )
    db_session.commit()

    found = get_vocab_by_surface_form("食べる", db_session)
    assert found is not None
    assert found.reading == "taberu"
    # assert get_vocab_by_surface_form("走る", db_session) is None


@pytest.mark.word_lookup
def test_get_vocab_by_surface_form_returns_none_if_not_found(db_session):
    db_session.add(
        Vocabulary(
            japanese_form="食べる",
            reading="taberu",
            meanings=[{"pos": "verb", "meanings": ["to eat"]}],
            estimated_level=EstimatedLevel.N5,
            lemma="食べる",
        )
    )
    db_session.commit()

    # found = get_vocab_by_surface_form("食べる", db_session)
    # assert found is not None
    # assert found.reading == "taberu"
    assert get_vocab_by_surface_form("走る", db_session) is None


# ==========================================================================
# docs/test_case_specification.pdf  MD-126  get_vocab_by_id()
#   - Vocabulary found by id
#   - Unknown vocabulary id
# Self-contained in-memory SQLite session (`vocab_db`).
# ==========================================================================
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


@pytest.fixture()
def vocab_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Vocabulary.__table__.create(engine)
    Session = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.mark.word_lookup
def test_get_vocab_by_id_returns_row(vocab_db):
    """The Vocabulary row is returned with its fields populated."""
    row = Vocabulary(
        japanese_form="食べる",
        reading="taberu",
        lemma="食べる",
        meanings=[{"pos": "verb", "meanings": ["to eat"]}],
        estimated_level=EstimatedLevel.N5,
    )
    vocab_db.add(row)
    vocab_db.commit()

    found = get_vocab_by_id(row.id, vocab_db)
    assert found is not None
    assert found.japanese_form == "食べる"
    assert found.reading == "taberu"
    assert found.lemma == "食べる"
    assert found.meanings == [{"pos": "verb", "meanings": ["to eat"]}]


@pytest.mark.word_lookup
def test_get_vocab_by_id_unknown_returns_none(vocab_db):
    """An unknown id yields None."""
    assert get_vocab_by_id(999, vocab_db) is None
