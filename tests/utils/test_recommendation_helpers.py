import datetime
from types import SimpleNamespace

import pytest

from core.recommendation_config import CONFIG, RecommendationConfig
from models.user import EstimatedLevel as UserLevel
from models.user_vocab_library import SRSState, UserSavedVocabulary
from models.user_vocab_profile import UserVocabularyExposure, VocabStatus
from models.vocab import EstimatedLevel as VocabLevel
from utils.recommendation_helpers import (
    cold_start_may_know_percent,
    comprehension_fit,
    compute_known_weight,
    coverage,
    difficulty_tag,
    due_factor,
    learning_value,
    level_fit,
    normalize_srs,
    recency_penalty,
    srs_review_bonus,
    struggle_factor,
)


# Test compute_known_weight
def test_compute_known_weight_more_mastered():
    exposure = UserVocabularyExposure(status=VocabStatus.seen, seen_count=8)
    saved = UserSavedVocabulary(srs_state=SRSState.mastered)
    weight = compute_known_weight(exposure, saved, CONFIG)
    assert weight == 1


def test_compute_known_weight_more_exposure():
    exposure = UserVocabularyExposure(status=VocabStatus.know)
    saved = UserSavedVocabulary(srs_state=SRSState.studying, interval_days=3)
    weight = compute_known_weight(exposure, saved, CONFIG)
    assert weight == 1


def test_compute_known_weight_less_than_1():
    exposure = UserVocabularyExposure(status=VocabStatus.seen, seen_count=8)
    saved = UserSavedVocabulary(srs_state=SRSState.studying, interval_days=3)
    weight = compute_known_weight(exposure, saved, CONFIG)
    assert weight < 1


def test_compute_known_weight_one_is_none():
    exposure = None
    saved = UserSavedVocabulary(srs_state=SRSState.mastered)
    weight = compute_known_weight(exposure, saved, CONFIG)
    assert weight == 1


def test_compute_known_weight_both_none():
    exposure = None
    saved = None
    weight = compute_known_weight(exposure, saved, CONFIG)
    assert weight == 0


# ------------------------------------------------------------

# test coverage


def test_coverage_normal():
    video_vocab_freq = {1: 10, 2: 20, 3: 10, 4: 10}
    known_map = {1: 1, 2: 0.6, 3: 1}
    cov = coverage(video_vocab_freq, known_map)
    assert cov == 32 / 50


def test_coverage_zero():
    video_vocab_freq = {1: 10, 2: 20, 3: 10, 4: 10}
    known_map = {5: 1}
    cov = coverage(video_vocab_freq, known_map)
    assert cov == 0


def test_coverage_no_video_vocab_freq():
    video_vocab_freq = {}
    known_map = {1: 1}
    cov = coverage(video_vocab_freq, known_map)
    assert cov == 0


# ----------------------------------------------------------------


# test comprehension fit
def test_comprehension_fit_harder():
    c = comprehension_fit(0.3, CONFIG)
    assert c == pytest.approx(8.364834723e-05)


def test_comprehension_fit_optimal():
    c = comprehension_fit(0.95, CONFIG)
    assert c == 1


def test_comprehension_fit_easier():
    c = comprehension_fit(0.98, CONFIG)
    assert c == pytest.approx(0.83527)


def test_comprehension_fit_zero():
    c = comprehension_fit(0, CONFIG)
    assert c == pytest.approx(1.9497e-9)


def test_comprehension_fit_one():
    c = comprehension_fit(1, CONFIG)
    assert c == pytest.approx(0.60653, abs=1e-05)


# ----------------------------------------------------------------------


# test level_fit
def test_level_fit_unknown_vocab():
    score = level_fit(VocabLevel.UNKNOWN, UserLevel.intermediate, CONFIG)
    assert score == 0.05


def test_level_fit_fit_vocab():
    score = level_fit(VocabLevel.N3, UserLevel.intermediate, CONFIG)
    assert score == 1


def test_level_fit_easier_vocab():
    score = level_fit(VocabLevel.N4, UserLevel.intermediate, CONFIG)
    assert score == 0.8


def test_level_fit_jump_easier_vocab():
    score = level_fit(VocabLevel.N5, UserLevel.advanced, CONFIG)
    assert score == 0.4096


def test_level_fit_harder_vocab():
    score = level_fit(VocabLevel.N1, UserLevel.intermediate, CONFIG)
    assert score == 0.5


def test_level_fit_jump_harder_vocab():
    score = level_fit(VocabLevel.N1, UserLevel.beginner, CONFIG)
    assert score == 0.125


def test_level_fit_intended_behaviour():
    score_unknown = level_fit(VocabLevel.UNKNOWN, UserLevel.beginner, CONFIG)
    score_fit = level_fit(VocabLevel.N3, UserLevel.intermediate, CONFIG)
    score_easier = level_fit(VocabLevel.N5, UserLevel.intermediate, CONFIG)
    score_harder = level_fit(VocabLevel.N1, UserLevel.intermediate, CONFIG)
    assert score_fit > score_easier > score_harder > score_unknown


# ----------------------------------------------------------------------------------


# test learning_value
def test_learning_value_zero_when_all_know():
    video_vocab_freq_best = {1: 10, 2: 12, 3: 2, 4: 10}
    known_map_best = {1: 1, 2: 1, 3: 1, 4: 1}
    word_level_best = {
        1: VocabLevel.N3,
        2: VocabLevel.N2,
        3: VocabLevel.N3,
        4: VocabLevel.N2,
    }
    user_level_best = UserLevel.intermediate
    lv_best = learning_value(
        video_vocab_freq_best, known_map_best, word_level_best, user_level_best, CONFIG
    )

    assert lv_best == 0


def test_learning_value_less_known_word_score_more():  # the `room` promise
    freqs, levels = {1: 5}, {1: VocabLevel.N4}
    unknown = learning_value(freqs, {}, levels, UserLevel.beginner)
    partial = learning_value(freqs, {1: 0.5}, levels, UserLevel.beginner)
    assert unknown > partial > 0


def test_learning_value_same_level_beats_above_level():  # the `room` promise
    freqs, levels = {1: 5}, {1: VocabLevel.N4}
    same_level = learning_value(freqs, {}, levels, UserLevel.beginner)
    above_level = learning_value(freqs, {}, levels, UserLevel.intermediate)
    assert same_level > above_level


def test_learning_value_zero_when_input_empty():
    lv = learning_value({}, {}, {}, UserLevel.beginner)
    assert lv == 0


# -----------------------------------------------------------------------------------------

# test due_factor


def test_due_factor_not_schedule():
    df = due_factor(None, datetime.datetime.utcnow())
    assert df == 0


def test_due_factor_not_due():
    df = due_factor(datetime.datetime(2026, 8, 20), datetime.datetime.utcnow())
    assert df == 0


def test_due_factor_due_now():
    df = due_factor(datetime.datetime.utcnow(), datetime.datetime.utcnow())
    assert df == 1


def test_due_factor_overdue():
    now = datetime.datetime(2026, 1, 15)
    assert due_factor(now - datetime.timedelta(days=3), now) > 1


def test_due_factor_overdue__cap_at_two():
    df = due_factor(datetime.datetime(2026, 8, 1), datetime.datetime.utcnow())
    assert df == 2


# -------------------------------------------------------------------------------

# test stuggle_factor


def test_struggle_factor_no_lapse():
    sf = struggle_factor(0)
    assert sf == 1


def test_struggle_factor_lapse():
    sf = struggle_factor(2)
    assert sf > 1


def test_struggle_factor_lapse_cap():
    sf = struggle_factor(10)
    assert sf == 2


# --------------------------------------------------------------------------------

# test srs_review_bonus
NOW = datetime.datetime.utcnow()


def card(vocab_id, days_overdue=0, lapses=0):
    return SimpleNamespace(
        vocab_id=vocab_id,
        next_review_date=NOW
        - datetime.timedelta(days=days_overdue),  # +overdue = past date
        lapses=lapses,
    )


def test_srs_review_word_not_in_video_is_ignored():
    assert srs_review_bonus([card(1, days_overdue=5)], set(), NOW) == 0.0
    assert srs_review_bonus([card(1, days_overdue=5)], {2, 3}, NOW) == 0.0


def test_srs_review_not_due_word_is_ignored():
    assert (
        srs_review_bonus([card(1, days_overdue=-3)], {1}, NOW) == 0.0
    )  # due in 3 days


def test_srs_review_due_word_contributes_due_times_struggle():  # anchors against the parts
    row = card(1, days_overdue=0, lapses=0)
    expected = due_factor(row.next_review_date, NOW) * struggle_factor(0)
    assert srs_review_bonus([row], {1}, NOW) == expected


def test_srs_review_more_overdue_scores_higher():
    a = srs_review_bonus([card(1, days_overdue=1)], {1}, NOW)
    b = srs_review_bonus([card(1, days_overdue=10)], {1}, NOW)
    assert b > a > 0


def test_srs_review_more_lapses_scores_higher():
    a = srs_review_bonus([card(1, days_overdue=2, lapses=0)], {1}, NOW)
    b = srs_review_bonus([card(1, days_overdue=2, lapses=4)], {1}, NOW)
    assert b > a


def test_srs_review_caps_at_max_words_per_video():
    cfg = RecommendationConfig(srs_max_words_per_video=2)
    rows = [card(i, days_overdue=5) for i in range(1, 6)]  # 5 identical due words
    one = srs_review_bonus([rows[0]], {1}, NOW, cfg)
    allw = srs_review_bonus(rows, {1, 2, 3, 4, 5}, NOW, cfg)
    assert allw == pytest.approx(2 * one)  # only the top 2 counted


# def test_cap_keeps_the_highest_contributions():
#     cfg = RecommendationConfig(srs_max_words_per_video=1)
#     small, big = card(1, days_overdue=1, lapses=0), card(2, days_overdue=10, lapses=5)
#     assert srs_review_bonus([small, big], {1, 2}, NOW, cfg) \
#         == srs_review_bonus([big], {2}, NOW, cfg)            # kept word is the big one


def test_srs_review_empty_and_no_matches():
    assert srs_review_bonus([], {1, 2}, NOW) == 0.0


# ----------------------------------------------------------------------------------


# test normalize_srs
def test_normalize_srs_zero_is_zero():
    assert normalize_srs(0.0) == 0.0


def test_normalize_srs_bounded_and_monotonic():
    vals = [normalize_srs(x) for x in (0, 1, 3, 6, 20)]
    assert all(0.0 <= v < 1.0 for v in vals)
    assert vals == sorted(vals)


# ------------------------------------------------------------------------------------

# test recency_penalty


def test_recency_penalty_no_watch_at_all():
    rp = recency_penalty(None, NOW)
    assert rp == 0


def test_recency_penalty_more_recent_more_penalty():
    long = datetime.datetime(2026, 8, 14)
    recent = datetime.datetime(2026, 8, 17)
    rp_long = recency_penalty(long, NOW)
    rp_recent = recency_penalty(recent, NOW)
    assert 0 <= rp_long < rp_recent <= 1


# ----------------------------------------------------------------------------------

# test difficulty_tag


def test_difficulty_each_bucket():
    assert difficulty_tag(0.98) == "comfortable"
    assert difficulty_tag(0.90) == "best_fit"
    assert difficulty_tag(0.78) == "stretch"
    assert difficulty_tag(0.40) == "too_advanced"


def test_difficulty_boundaries_are_inclusive_lower():
    # a value exactly on a threshold falls into the HIGHER bucket
    assert difficulty_tag(CONFIG.difficulty_comfortable_min) == "comfortable"  # 0.95
    assert difficulty_tag(CONFIG.difficulty_best_fit_min) == "best_fit"  # 0.85
    assert difficulty_tag(CONFIG.difficulty_stretch_min) == "stretch"  # 0.70


def test_difficulty_just_below_each_boundary():
    assert difficulty_tag(0.94999) == "best_fit"
    assert difficulty_tag(0.84999) == "stretch"
    assert difficulty_tag(0.69999) == "too_advanced"


def test_difficulty_extremes():
    assert difficulty_tag(1.0) == "comfortable"
    assert difficulty_tag(0.0) == "too_advanced"


def test_difficulty_never_gets_harder_as_coverage_rises():
    order = ["too_advanced", "stretch", "best_fit", "comfortable"]
    tags = [difficulty_tag(c) for c in (0.50, 0.75, 0.90, 0.98)]
    assert [order.index(t) for t in tags] == [0, 1, 2, 3]  # strictly improving


# --- cold_start_may_know_percent ---


def test_may_know_all_at_or_below_level_is_100():
    freqs = {1: 5, 2: 5}
    levels = {1: VocabLevel.N5, 2: VocabLevel.N4}  # beginner band = N4-N5
    assert cold_start_may_know_percent(freqs, levels, UserLevel.beginner) == 100


def test_may_know_all_above_level_is_0():
    freqs = {1: 5, 2: 5}
    levels = {1: VocabLevel.N3, 2: VocabLevel.N1}  # all harder than beginner
    assert cold_start_may_know_percent(freqs, levels, UserLevel.beginner) == 0


def test_may_know_is_frequency_weighted_not_type_count():
    # one very frequent at-level word + one rare hard word
    freqs = {1: 90, 2: 10}
    levels = {1: VocabLevel.N5, 2: VocabLevel.N1}
    assert (
        cold_start_may_know_percent(freqs, levels, UserLevel.beginner) == 90
    )  # 90/100 tokens


def test_may_know_unknown_tier_does_not_count():
    freqs = {1: 50, 2: 50}
    levels = {1: VocabLevel.N5, 2: VocabLevel.UNKNOWN}
    assert cold_start_may_know_percent(freqs, levels, UserLevel.beginner) == 50


def test_may_know_higher_level_counts_more_tiers():
    freqs = {1: 50, 2: 50}
    levels = {1: VocabLevel.N5, 2: VocabLevel.N2}
    # beginner: only N5 is at/below -> 50 ; intermediate (N2-N3): N5(below) + N2 -> 100
    assert cold_start_may_know_percent(freqs, levels, UserLevel.beginner) == 50
    assert cold_start_may_know_percent(freqs, levels, UserLevel.intermediate) == 100


def test_may_know_rounds_to_int():
    freqs = {1: 1, 2: 2}  # 1 of 3 tokens -> 33.33
    levels = {1: VocabLevel.N5, 2: VocabLevel.N1}
    assert cold_start_may_know_percent(freqs, levels, UserLevel.beginner) == 33


def test_may_know_empty_video_is_0():
    assert cold_start_may_know_percent({}, {}, UserLevel.beginner) == 0
