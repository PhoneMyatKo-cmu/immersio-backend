"""Tunable parameters for the personalized video recommendation algorithm.

All "magic numbers" for scoring live here so they can be calibrated without
touching logic. Values are *starting points*: the pedagogical framing (band
shape, coverage target, encounter counts) is research-backed, but every concrete
constant is a placeholder to tune against real usage.

See the design notes for the four scoring forces:
    ComprehensionFit  (band, §3) + LearningValue (§4) + SRSReviewBonus (§5)
    - RecencyPenalty  (§6)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RecommendationConfig:
    # ------------------------------------------------------------------ #
    # Serving model
    # ------------------------------------------------------------------ #
    # DECISION: compute scores on demand per request (no precomputed cache
    # table for now). Revisit if per-request latency becomes a problem.
    serving_mode: str = "on_demand"

    # ------------------------------------------------------------------ #
    # Hard pre-filters (candidate selection, §7)
    # ------------------------------------------------------------------ #
    # DECISION: only these two cheap SQL filters for now. The comprehension
    # floor is intentionally NOT a hard filter yet — low-coverage videos are
    # allowed through and simply score poorly via the band below.
    filter_require_active: bool = True
    filter_require_shadowing_ready: bool = True

    # ------------------------------------------------------------------ #
    # known_weight: collapsing user state into [0, 1] per word (§2)
    # ------------------------------------------------------------------ #
    # DECISION: passive exposure is treated as equal to SRS-mastered, so an
    # exposure status of KNOW maps to full 1.0 just like a mastered card.
    weight_know: float = 1.0  # exposure status == KNOW
    weight_mastered: float = 1.0  # SRS srs_state == mastered

    # Partial credit for words only partially known:
    #   SEEN (exposure): base + step * seen_count, capped below KNOW.
    seen_base: float = 0.30
    seen_step: float = 0.05
    seen_cap: float = 0.80
    #   studying (SRS): min(1.0, interval_days / interval_full_days).
    srs_interval_full_days: int = 21

    # ------------------------------------------------------------------ #
    # ComprehensionFit band (§3)
    # ------------------------------------------------------------------ #
    # DECISION: target coverage 0.95 (listening-calibrated; Nation/Laufer put
    # ~95% as sufficient for listening comprehension).
    comprehension_mu: float = 0.95
    # Asymmetric band: wider left tail (too-hard falls off gently until it's
    # really incomprehensible), narrower right tail (mild penalty as C -> 1.0
    # so "nothing new to learn" videos are demoted, not banned).
    comprehension_sigma_left: float = 0.15  # for C < mu (too hard)
    comprehension_sigma_right: float = 0.05  # for C > mu (too easy)

    # ------------------------------------------------------------------ #
    # LearningValue (§4)
    # ------------------------------------------------------------------ #
    # DECISION: working level is the STATIC level the user sets (no dynamic
    # estimate yet — revisit later). level_fit is computed relative to it.
    # JLPT tiers are ranked N5=5 (easiest) .. N1=1 (hardest); a word "above"
    # the user's level is harder (lower tier number).
    level_fit_same: float = 1.0
    level_fit_step_harder: float = 0.5  # multiplier per tier ABOVE user level
    level_fit_step_easier: float = 0.8  # multiplier per tier BELOW user level
    level_fit_unknown: float = 0.05  # Vocabulary.estimated_level == UNKNOWN

    # A word must appear at least this many times in a video to count as a
    # realistic learning target (incidental-acquisition research: ~8-12+
    # encounters; kept at 1 for now so nothing is dropped, tune upward later).
    learnable_min_freq: int = 1

    # ------------------------------------------------------------------ #
    # SRSReviewBonus (§5)
    # ------------------------------------------------------------------ #
    # Overdue ramp: due_factor is 0 before due date, 1.0 on the due date,
    # growing up to overdue_cap as a word becomes more overdue.
    srs_overdue_cap: float = 2.0
    srs_overdue_days_to_cap: int = 14
    # Struggle amplifier from SM-2 lapses / ease_factor.
    srs_struggle_per_lapse: float = 0.2
    srs_struggle_cap: float = 2.0
    # Cap distinct deck words counted per video so one word-stuffed video
    # can't dominate the SRS term.
    srs_max_words_per_video: int = 5

    # Normalization: squash the raw bonus into [0, 1] so weights stay pure
    # business priority. Higher = slower saturation (raw bonus must be larger
    # to approach 1). ~3.0 means a couple of due words already scores well.
    srs_saturation: float = 3.0

    # ------------------------------------------------------------------ #
    # RecencyPenalty (§6)
    # ------------------------------------------------------------------ #
    # Penalty = exp(-days_since_last_watch / tau). Just-watched -> ~1.0,
    # recovers over ~a week.
    recency_tau_days: float = 7.0

    # ------------------------------------------------------------------ #
    # Final weighted score
    # ------------------------------------------------------------------ #
    #   score = w_ci*CI + w_learn*Learn + w_srs*SRS - w_recency*Recency
    # DECISION: weight learning value above the SRS review bonus (discovery-
    # leaning feed).
    w_ci: float = 1.0
    w_learn: float = 0.6
    w_srs: float = 0.3
    w_recency: float = 0.5

    # ------------------------------------------------------------------ #
    # Cold start (§8)
    # ------------------------------------------------------------------ #
    # Below this many known words, fall back toward curated/level-based ranking
    # and blend into the personalized score as the profile grows.
    cold_start_min_profile: int = 50

    # ------------------------------------------------------------------ #
    # Feed layout & difficulty tags (display only — not used in scoring)
    # ------------------------------------------------------------------ #
    hero_size: int = 8  # videos in the "Top picks" row
    row_size: int = 12  # videos per difficulty row

    # Difficulty tag thresholds, on coverage. Backend owns these so the
    # label rule lives in one place.
    difficulty_comfortable_min: float = 0.95  # >= this -> comfortable
    difficulty_best_fit_min: float = 0.85  # >= this -> best_fit
    difficulty_stretch_min: float = 0.70  # >= this -> stretch; below -> too_advanced

    # Recency hard cutoff: videos watched within this window are excluded
    # outright (the additive penalty can't reliably suppress a high-CI video).
    # Set 0 to disable. The soft recency_penalty still handles the tail after.
    recency_hard_filter_hours: float = 0.0

    # Cutoff min profile to dcide cold start or not
    cold_start_min_profile = 50


# Singleton used across the recommendation service. Import this, don't
# re-instantiate, so all layers read the same tuned values.
CONFIG = RecommendationConfig()
