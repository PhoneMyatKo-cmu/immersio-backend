"""Pure scoring helpers for the recommendation algorithm (no DB access).

Everything here takes plain values / ORM rows and returns numbers, so it can be
unit-tested without a database.
"""

from core.recommendation_config import CONFIG, RecommendationConfig
from models.user_vocab_library import SRSState, UserSavedVocabulary
from models.user_vocab_profile import UserVocabularyExposure, VocabStatus


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
