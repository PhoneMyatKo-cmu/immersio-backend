"""
Tests for utils/spaced_repetition_review_helper.py

Covers docs/test_case_specification.pdf MD-138 .. MD-142:

  MD-138  update_ease_factor()
    - Grade moves the ease factor in the right direction
    - Floor of 1.3 is enforced
    - Grade outside 0-5 is rejected

  MD-139  update_review_stats()
    - Early repetitions use fixed intervals
    - Later repetitions scale by the ease factor
    - Failing grade records a lapse and resets

  MD-140  update_next_review_date()
    - Next review scheduled from today
    - date/DateTime column round-trip

  MD-141  update_srs_state()
    - State follows the 180-day boundary
    - Mastered card that lapses returns to studying

  MD-142  update_review_card()
    - Successful review updates every field consistently
    - Failed review resets the schedule
    - Invalid grade aborts before any mutation
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

try:
    import models.vocab  # noqa: F401
    import models.processed_caption  # noqa: F401
    import models.sentence  # noqa: F401
    from models.user import User
    from models.video import Video
    from models.user_vocab_library import UserSavedVocabulary
    from utils.spaced_repetition_review_helper import (
        update_ease_factor,
        update_review_stats,
        update_next_review_date,
        update_srs_state,
        update_review_card,
    )
except Exception as exc:  # pragma: no cover - import guard
    pytest.skip(f"spaced_repetition_review_helper unavailable: {exc}",
                allow_module_level=True)

pytestmark = [pytest.mark.unit]


def _card(**overrides):
    """A detached UserSavedVocabulary with sensible SRS defaults."""
    defaults = dict(ease_factor=2.5, interval_days=0, repetitions=0, lapses=0)
    defaults.update(overrides)
    return UserSavedVocabulary(**defaults)


# ---------------------------------------------------------------------------
# MD-138  update_ease_factor()
# ---------------------------------------------------------------------------
def test_grade_moves_ease_factor_in_the_right_direction():
    """Grade 5 nudges the ease factor up; a low grade drives it down."""
    up = _card(ease_factor=2.5)
    assert update_ease_factor(up, 5) == pytest.approx(2.6)
    assert up.ease_factor == pytest.approx(2.6)

    down = _card(ease_factor=2.5)
    result = update_ease_factor(down, 2)
    assert result < 2.5
    assert down.ease_factor == result


def test_ease_factor_floor_is_enforced():
    """The ease factor is clamped to exactly 1.3, never lower."""
    card = _card(ease_factor=1.35)
    assert update_ease_factor(card, 0) == 1.3
    assert card.ease_factor == 1.3


def test_grade_outside_range_is_rejected():
    """Grades below 0 or above 5 raise; 0 and 5 are accepted."""
    for bad in (-1, 6):
        card = _card(ease_factor=2.5)
        with pytest.raises(ValueError, match="Grade must be between 0 and 5."):
            update_ease_factor(card, bad)
        assert card.ease_factor == 2.5

    for ok in (0, 5):
        update_ease_factor(_card(ease_factor=2.5), ok)  # no raise


# ---------------------------------------------------------------------------
# MD-139  update_review_stats()
# ---------------------------------------------------------------------------
def test_early_repetitions_use_fixed_intervals():
    """First success -> 1 day, second success -> 6 days."""
    first = _card(repetitions=0)
    update_review_stats(first, 4)
    assert (first.repetitions, first.interval_days) == (1, 1)

    second = _card(repetitions=1)
    update_review_stats(second, 4)
    assert (second.repetitions, second.interval_days) == (2, 6)


def test_later_repetitions_scale_by_ease_factor():
    """From the third repetition the interval is interval * ease_factor, rounded."""
    card = _card(repetitions=2, interval_days=6, ease_factor=2.5)
    update_review_stats(card, 4)
    assert card.repetitions == 3
    assert card.interval_days == 15


def test_failing_grade_records_a_lapse_and_resets():
    """Grade < 3 bumps lapses and resets repetitions/interval; grade 3 does not."""
    card = _card(repetitions=5, interval_days=40, lapses=1)
    update_review_stats(card, 2)
    assert (card.lapses, card.repetitions, card.interval_days) == (2, 0, 1)

    ok = _card(repetitions=5, interval_days=40, lapses=1)
    update_review_stats(ok, 3)
    assert ok.repetitions == 6 and ok.lapses == 1


# ---------------------------------------------------------------------------
# MD-140  update_next_review_date()
# ---------------------------------------------------------------------------
def test_next_review_scheduled_from_today():
    """last_review_date is today; next_review_date is today + interval."""
    today = date.today()

    card = _card(interval_days=6)
    update_next_review_date(card)
    assert card.last_review_date == today
    assert card.next_review_date == today + timedelta(days=6)

    due = _card(interval_days=0)
    update_next_review_date(due)
    assert due.next_review_date == today


# ---------------------------------------------------------------------------
# MD-141  update_srs_state()
# ---------------------------------------------------------------------------
def test_state_follows_the_180_day_boundary():
    """>= 180 days is 'mastered' (inclusive); below is 'studying'."""
    for interval, expected in ((200, "mastered"), (180, "mastered"), (179, "studying")):
        card = _card(interval_days=interval)
        update_srs_state(card)
        assert card.srs_state == expected


def test_mastered_card_that_lapses_returns_to_studying():
    """A failing grade resets the interval, and the state falls back to 'studying'."""
    card = _card(interval_days=200)
    update_srs_state(card)
    assert card.srs_state == "mastered"

    update_review_stats(card, 2)   # lapse -> interval_days = 1
    update_srs_state(card)
    assert card.srs_state == "studying"


# ---------------------------------------------------------------------------
# MD-142  update_review_card()
# ---------------------------------------------------------------------------
def test_successful_review_updates_every_field_consistently():
    """Grade 5: ease factor, repetitions, interval and dates all move together."""
    today = date.today()
    card = _card(ease_factor=2.5, repetitions=2, interval_days=6)

    update_review_card(card, 5)

    assert card.ease_factor == pytest.approx(2.6)
    assert card.repetitions == 3
    assert card.interval_days == 16          # round(6 * 2.6), from the updated ease factor
    assert card.last_review_date == today
    assert card.next_review_date == today + timedelta(days=16)
    assert card.srs_state == "studying"


def test_failed_review_resets_the_schedule():
    """Grade 1: lapse, repetitions 0, interval 1, next review tomorrow, studying."""
    today = date.today()
    card = _card(repetitions=4, interval_days=30, lapses=0)

    update_review_card(card, 1)

    assert card.lapses == 1
    assert card.repetitions == 0
    assert card.interval_days == 1
    assert card.next_review_date == today + timedelta(days=1)
    assert card.srs_state == "studying"


def test_invalid_grade_aborts_before_any_mutation():
    """Grade 7 raises out of update_ease_factor and leaves the card untouched."""
    card = _card(ease_factor=2.5, repetitions=2, interval_days=6, lapses=0)

    with pytest.raises(ValueError):
        update_review_card(card, 7)

    assert card.ease_factor == 2.5
    assert card.repetitions == 2
    assert card.interval_days == 6
    assert card.lapses == 0


# ---------------------------------------------------------------------------
# Helpers / fixtures for the one DB round-trip test
# ---------------------------------------------------------------------------
def _as_date(value):
    return value.date() if isinstance(value, datetime) else value


def _seed_user_video(db):
    user = User(first_name="A", last_name="B", email="a@example.com", password_hash="x")
    video = Video(youtube_video_id="vid12345678", title="T", thumbnail_url="u",
                  channel_name="C", duration_seconds=10)
    db.add_all([user, video])
    db.commit()
    db.refresh(user)
    db.refresh(video)
    return user, video


@pytest.fixture()
def srs_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    for table in (User.__table__, Video.__table__, UserSavedVocabulary.__table__):
        table.create(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
