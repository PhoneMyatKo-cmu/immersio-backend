"""Pure scoring helpers for the recommendation algorithm (no DB access).

Everything here takes plain values / ORM rows and returns numbers, so it can be
unit-tested without a database.
"""

import math
from datetime import datetime

from core.recommendation_config import CONFIG, RecommendationConfig
from models.user import EstimatedLevel as UserLevel
from models.user_vocab_library import SRSState, UserSavedVocabulary
from models.user_vocab_profile import UserVocabularyExposure, VocabStatus
from models.vocab import EstimatedLevel as VocabLevel

# JLPT tiers ranked so a HIGHER number is EASIER (N5=5 .. N1=1).
_JLPT_RANK: dict[VocabLevel, int] = {
    VocabLevel.N5: 5,
    VocabLevel.N4: 4,
    VocabLevel.N3: 3,
    VocabLevel.N2: 2,
    VocabLevel.N1: 1,
}

# A coarse user level spans a BAND of JLPT ranks (inclusive low, high).
#   beginner -> N5,N4 ; intermediate -> N3,N2 ; advanced -> N1
_USER_LEVEL_BANDS: dict[UserLevel, tuple[int, int]] = {
    UserLevel.beginner: (4, 5),  # N4..N5
    UserLevel.intermediate: (2, 3),  # N2..N3
    UserLevel.advanced: (1, 1),  # N1
}


# build known weight from which the rest of scoring function reference
def compute_known_weight(
    exposure: UserVocabularyExposure | None,
    library: UserSavedVocabulary | None,
    cfg: RecommendationConfig = CONFIG,
) -> float:
    """Collapse a user's state for one word into a single known-ness in [0, 1].

    Two independent sources of evidence are combined by taking the MAX — more
    evidence should never lower the estimate:

      * exposure (passive):  KNOW -> full; SEEN -> ramps with seen_count.
      * library (SRS deck):  mastered -> full; studying -> ramps with the
                             review interval; new/not-studied -> 0.

    Per config, passive KNOW is treated as equal to SRS-mastered (both 1.0).
    Returns 0.0 when the word is absent from both tables (never encountered).
    """
    exposure_weight = _exposure_weight(exposure, cfg)
    library_weight = _library_weight(library, cfg)
    return _clamp01(max(exposure_weight, library_weight))


def _exposure_weight(
    exposure: UserVocabularyExposure | None, cfg: RecommendationConfig
) -> float:
    if exposure is None:
        return 0.0
    if exposure.status == VocabStatus.know:
        return cfg.weight_know
    # SEEN: partial credit that ramps with sightings, capped below KNOW.
    return min(cfg.seen_cap, cfg.seen_base + cfg.seen_step * exposure.seen_count)


def _library_weight(
    library: UserSavedVocabulary | None, cfg: RecommendationConfig
) -> float:
    if library is None or library.is_deleted:
        return 0.0
    if library.srs_state == SRSState.mastered:
        return cfg.weight_mastered
    if library.srs_state == SRSState.studying:
        # A word on a long review interval is effectively known.
        return min(1.0, library.interval_days / cfg.srs_interval_full_days)
    return 0.0  # new / not_studied


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


# Comprehension Score
def coverage(video_vocab_freqs: dict[int, int], known: dict[int, float]) -> float:
    """Frequency-weighted comprehension coverage C in [0, 1] (§3).

    Fraction of the video's *tokens* the user understands: each word weighted by
    how often it occurs, so a few high-frequency words dominate — matching how
    the lexical-coverage literature defines text coverage.
    """
    total = sum(video_vocab_freqs.values())
    if total == 0:
        return 0.0  # empty / unprofiled video

    understood = sum(
        freq * known.get(vocab_id, 0.0) for vocab_id, freq in video_vocab_freqs.items()
    )
    return understood / total


def comprehension_fit(c: float, cfg: RecommendationConfig = CONFIG) -> float:
    """Map coverage C onto the Krashen/ZPD band, peaking at cfg.comprehension_mu.

    Asymmetric Gaussian: wider left tail (too-hard falls off gently until truly
    incomprehensible), narrower right tail (mild penalty as C -> 1.0 so
    "nothing new to learn" videos are demoted, not banned). Returns [0, 1].
    """
    sigma = (
        cfg.comprehension_sigma_left
        if c <= cfg.comprehension_mu
        else cfg.comprehension_sigma_right
    )
    return math.exp(-((c - cfg.comprehension_mu) ** 2) / (2 * sigma**2))


# Learning Value
def level_fit(
    word_level: VocabLevel,
    user_level: UserLevel,
    cfg: RecommendationConfig = CONFIG,
) -> float:
    """How level-appropriate an unknown word is for this user (§4), in [0, 1].

    The user's coarse level maps to a BAND of JLPT tiers. A word inside the band
    is "at level" (1.0); harder words (below the band) decay steeply, easier
    words (above it) decay gently. Unknown-tier words get a small floor.
    """
    if word_level == VocabLevel.UNKNOWN:
        return cfg.level_fit_unknown

    word_rank = _JLPT_RANK.get(word_level)
    band = _USER_LEVEL_BANDS.get(user_level)
    if word_rank is None or band is None:
        return cfg.level_fit_same  # neutral fallback

    low, high = band
    if low <= word_rank <= high:
        return cfg.level_fit_same
    if word_rank < low:  # harder than the band
        return cfg.level_fit_same * cfg.level_fit_step_harder ** (low - word_rank)
    return cfg.level_fit_same * cfg.level_fit_step_easier ** (
        word_rank - high
    )  # easier


def learning_value(
    video_vocab_freqs: dict[int, int],
    known: dict[int, float],
    word_levels: dict[int, VocabLevel],
    user_level: UserLevel,
    cfg: RecommendationConfig = CONFIG,
) -> float:
    """The "+1": value of the words the user does NOT yet fully know (§4).

    Each not-fully-known word contributes  room_to_learn * frequency * level_fit,
    where room_to_learn = (1 - known_weight). Normalized by total tokens so long
    videos don't win on sheer volume.
    """
    total = sum(video_vocab_freqs.values())
    if total == 0:
        return 0.0

    value = 0.0
    for vocab_id, freq in video_vocab_freqs.items():
        if freq < cfg.learnable_min_freq:
            continue
        room = 1.0 - known.get(vocab_id, 0.0)
        if room <= 0.0:
            continue  # already fully known
        word_level = word_levels.get(vocab_id, VocabLevel.UNKNOWN)
        value += room * freq * level_fit(word_level, user_level, cfg)

    return value / total


# Spaced-Repetition Review Bonus (§5)
def due_factor(
    next_review_date: datetime | None,
    now: datetime,
    cfg: RecommendationConfig = CONFIG,
) -> float:
    """How 'due' an SRS card is: 0 before its review date, 1.0 on the day,
    ramping up to cfg.srs_overdue_cap as it becomes more overdue.
    """
    if next_review_date is None:
        return 0.0  # never scheduled

    overdue_days = (now - next_review_date).total_seconds() / 86400.0
    if overdue_days < 0:
        return 0.0  # not due yet

    ramp = min(1.0, overdue_days / cfg.srs_overdue_days_to_cap)
    return 1.0 + (cfg.srs_overdue_cap - 1.0) * ramp


def struggle_factor(lapses: int, cfg: RecommendationConfig = CONFIG) -> float:
    """Amplify words the user keeps forgetting: 1.0 with no lapses, growing
    per lapse up to cfg.srs_struggle_cap.
    """
    return min(cfg.srs_struggle_cap, 1.0 + cfg.srs_struggle_per_lapse * lapses)


def normalize_srs(raw_bonus: float, cfg: RecommendationConfig = CONFIG) -> float:
    """Squash the raw SRS bonus into [0, 1] via exponential saturation.

    Keeps the SRS term on the same scale as comprehension_fit / recency so the
    final weights express priority only, not scale-conversion.
    """
    return 1.0 - math.exp(-raw_bonus / cfg.srs_saturation)


def srs_review_bonus(
    studying_rows: list[UserSavedVocabulary],
    video_vocab_ids: set[int],
    now: datetime,
    cfg: RecommendationConfig = CONFIG,
) -> float:
    """Reward a video for surfacing DUE, struggling deck words (§5).

    Each due studying card present in the video contributes
    due_factor * struggle_factor; only the top cfg.srs_max_words_per_video
    contributions count so one word-stuffed video can't dominate.
    """
    contributions: list[float] = []
    for row in studying_rows:
        if row.vocab_id not in video_vocab_ids:
            continue
        due = due_factor(row.next_review_date, now, cfg)
        if due <= 0.0:
            continue  # in the deck but not due yet
        contributions.append(due * struggle_factor(row.lapses, cfg))

    contributions.sort(reverse=True)
    return sum(contributions[: cfg.srs_max_words_per_video])


# Recency Penalty (§6)
def recency_penalty(
    last_watched: datetime | None,
    now: datetime,
    cfg: RecommendationConfig = CONFIG,
) -> float:
    """Suppress recently-watched videos, decaying over time (§6).

    exp(-days_since_watch / tau): ~1.0 just after watching, recovering toward 0
    over roughly cfg.recency_tau_days. Never-watched videos get 0 (no penalty).
    """
    if last_watched is None:
        return 0.0

    days = max(0.0, (now - last_watched).total_seconds() / 86400.0)
    return math.exp(-days / cfg.recency_tau_days)


def difficulty_tag(c: float, cfg: RecommendationConfig = CONFIG) -> str:
    """Map coverage to a learner-facing difficulty bucket (display only)."""
    if c >= cfg.difficulty_comfortable_min:
        return "comfortable"
    if c >= cfg.difficulty_best_fit_min:
        return "best_fit"
    if c >= cfg.difficulty_stretch_min:
        return "stretch"
    return "too_advanced"
