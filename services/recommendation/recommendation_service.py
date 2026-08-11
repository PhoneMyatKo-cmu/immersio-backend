from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.recommendation_config import CONFIG, RecommendationConfig
from models.user import EstimatedLevel as UserLevel
from models.user_vocab_library import UserSavedVocabulary
from models.video_vocab_profile import VideoVocabulary
from models.vocab import EstimatedLevel as VocabLevel
from models.vocab import Vocabulary
from schemas.recommendation import RecommendationResponse, RecommendedVideo
from schemas.user import UserRead
from services.user_vocab.user_vocab_service import get_user_saved_vocab
from services.user_vocab_exposure.user_vocab_exposure_service import (
    get_vocab_exposure_by_user,
)
from services.video.video_services import get_videos
from utils.recommendation_helpers import (
    comprehension_fit,
    compute_known_weight,
    coverage,
    learning_value,
    normalize_srs,
    recency_penalty,
    srs_review_bonus,
)


def get_recommended_videos(
    current_user: UserRead, db: Session
) -> RecommendationResponse:
    vocab_weights = get_vocab_weights(current_user.id, db)

    return RecommendationResponse()


def get_vocab_weights(user_id: int, db: Session):
    exposed_vocab = get_vocab_exposure_by_user(user_id, db)
    saved_vocab = get_user_saved_vocab(user_id, db)
    # known_weights=compute_known_weight(exposed_vocab,saved_vocab)
    exposure_by_vocab = {e.vocab_id: e for e in exposed_vocab}
    library_by_vocab = {lib.vocab_id: lib for lib in saved_vocab}

    known_map: dict[int, float] = {}
    for vocab_id in exposure_by_vocab.keys() | library_by_vocab.keys():
        weight = compute_known_weight(
            exposure_by_vocab.get(vocab_id),
            library_by_vocab.get(vocab_id),
        )
        if weight > 0.0:
            known_map[vocab_id] = weight

    return known_map


def _load_video_vocab(
    video_id: int, db: Session
) -> tuple[dict[int, int], dict[int, VocabLevel]]:
    """Per-word frequency + JLPT tier for one video, in a single join."""
    rows = db.execute(
        select(
            VideoVocabulary.vocab_id,
            VideoVocabulary.frequency,
            Vocabulary.estimated_level,
        )
        .join(Vocabulary, Vocabulary.id == VideoVocabulary.vocab_id)
        .where(VideoVocabulary.video_id == video_id)
    ).all()

    freqs: dict[int, int] = {}
    levels: dict[int, VocabLevel] = {}
    for vocab_id, frequency, level in rows:
        freqs[vocab_id] = frequency
        levels[vocab_id] = level
    return freqs, levels


def score_video(
    video_id: int,
    known_map: dict[int, float],
    studying_rows: list[UserSavedVocabulary],
    last_watched: datetime | None,
    user_level: UserLevel,
    now: datetime,
    db: Session,
    cfg: RecommendationConfig = CONFIG,
) -> dict[str, float]:
    """Full recommendation score for one video (§3–§6 combined).

        score = w_ci*CI + w_learn*Learn + w_srs*SRS - w_recency*Recency

    All per-user artifacts (known_map, studying_rows, last_watched, user_level,
    now) are built ONCE per request by the orchestrator and passed in; this
    function only does the per-video work. Returns the final score plus every
    component (maps directly onto RecommendationReasons for an explainable feed).
    """
    video_vocab_freqs, word_levels = _load_video_vocab(video_id, db)
    video_vocab_ids = set(video_vocab_freqs.keys())

    c = coverage(video_vocab_freqs, known_map)
    ci = comprehension_fit(c, cfg)
    learn = learning_value(video_vocab_freqs, known_map, word_levels, user_level, cfg)
    srs_raw = srs_review_bonus(studying_rows, video_vocab_ids, now, cfg)
    srs = normalize_srs(srs_raw, cfg)
    recency = recency_penalty(last_watched, now, cfg)

    score = (
        cfg.w_ci * ci + cfg.w_learn * learn + cfg.w_srs * srs - cfg.w_recency * recency
    )

    return {
        "score": score,
        "coverage": c,
        "comprehension_fit": ci,
        "learning_value": learn,
        "srs_bonus": srs,
        "recency_penalty": recency,
    }
