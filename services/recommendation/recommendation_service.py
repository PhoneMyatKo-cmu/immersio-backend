from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.recommendation_config import CONFIG, RecommendationConfig
from models.user import EstimatedLevel as UserLevel
from models.user_vocab_library import UserSavedVocabulary
from models.video_vocab_profile import VideoVocabulary
from models.vocab import EstimatedLevel as VocabLevel
from models.vocab import Vocabulary
from schemas.recommendation import (
    RecommendationFeed,
    RecommendationReasons,
    RecommendationResponse,
    RecommendationSection,
    RecommendedVideo,
)
from schemas.user import UserRead
from schemas.video import VideoResponse
from services.session.session_service import last_watched_map
from services.user_vocab.user_vocab_service import (
    get_studying_vocab_by_user,
    get_user_saved_vocab,
)
from services.user_vocab_exposure.user_vocab_exposure_service import (
    get_vocab_exposure_by_user,
)
from services.video.video_services import (
    get_video_eligible_for_recommendation,
    get_videos,
)
from utils.recommendation_helpers import (
    comprehension_fit,
    compute_known_weight,
    coverage,
    difficulty_tag,
    due_factor,
    learning_value,
    normalize_srs,
    recency_penalty,
    srs_review_bonus,
)


def _to_item(video, result, cfg) -> RecommendedVideo:
    cov = result["coverage"]
    return RecommendedVideo(
        id=video.id,
        video=VideoResponse.model_validate(video),
        score=result["score"],
        understand_percent=round(cov * 100),
        difficulty=difficulty_tag(cov, cfg),
        new_word_count=result["new_word_count"],
        review_word_count=result["review_word_count"],
        reasons=None,  # populate only in a debug mode
    )


def get_recommended_videos(
    current_user: UserRead, db: Session, page: int = 1, page_size: int = 6
) -> RecommendationFeed:
    vocab_weights = get_vocab_weights(current_user.id, db)
    candidate_videos = get_video_eligible_for_recommendation(db)
    studying_vocabs = get_studying_vocab_by_user(current_user.id, db)
    last_watch_video_map = last_watched_map(current_user.id, db)

    recency_cutoff = datetime.utcnow() - timedelta(
        hours=CONFIG.recency_hard_filter_hours
    )
    score = []
    for video in candidate_videos:
        last = last_watch_video_map.get(video.id)
        if (
            CONFIG.recency_hard_filter_hours > 0
            and last is not None
            and last >= recency_cutoff
        ):
            continue
        result = score_video(
            video_id=video.id,
            known_map=vocab_weights,
            studying_rows=studying_vocabs,
            last_watched=last_watch_video_map.get(video.id),
            user_level=current_user.estimated_level,
            now=datetime.utcnow(),
            db=db,
            cfg=CONFIG,
        )
        score.append((video, result))

    score.sort(key=lambda pair: pair[1]["score"], reverse=True)

    # enrich into items, in rank order
    ranked = [_to_item(video, result, CONFIG) for video, result in score]

    # hero row: top N by score,
    hero = [it for it in ranked if it.difficulty][: CONFIG.hero_size]

    # difficulty buckets (score order preserved from `ranked`)
    def bucket(tag: str) -> list[RecommendedVideo]:
        return [it for it in ranked if it.difficulty == tag]

    best_fit, stretch, comfortable = (
        bucket("best_fit"),
        bucket("stretch"),
        bucket("comfortable"),
    )

    sections = [
        RecommendationSection(
            key="top_picks", title="Top picks for you", total=len(hero), items=hero
        ),
        RecommendationSection(
            key="best_fit",
            title="Just Right",
            total=len(best_fit),
            items=best_fit[: CONFIG.row_size],
        ),
        RecommendationSection(
            key="stretch",
            title="Challenge",
            total=len(stretch),
            items=stretch[: CONFIG.row_size],
        ),
        RecommendationSection(
            key="comfortable",
            title="Easy For You",
            total=len(comfortable),
            items=comfortable[: CONFIG.row_size],
        ),
    ]
    sections = [s for s in sections if s.items]  # drop empty rows

    return RecommendationFeed(sections=sections)

    # total = len(score)
    # total_pages = (total + page_size - 1) // page_size
    # start = (page - 1) * page_size
    # page_slice = score[start : start + page_size]

    # items = [
    #     RecommendedVideo(
    #         id=video.id,
    #         video=VideoResponse.model_validate(video),
    #         score=result["score"],
    #         reasons=RecommendationReasons(
    #             **{k: v for k, v in result.items() if k != "score"}
    #         ),
    #     )
    #     for video, result in page_slice
    # ]

    # return RecommendationResponse(
    #     items=items, page=page, page_size=page_size, total_pages=total_pages
    # )


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
            known_map[int(vocab_id)] = weight

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

    new_word_count = sum(
        1
        for vid, freq in video_vocab_freqs.items()
        if freq >= cfg.learnable_min_freq and known_map.get(vid, 0.0) < 1.0
    )
    review_word_count = sum(
        1
        for row in studying_rows
        if row.vocab_id in video_vocab_ids
        and due_factor(row.next_review_date, now, cfg) > 0.0
    )

    return {
        "score": score,
        "coverage": c,
        "comprehension_fit": ci,
        "learning_value": learn,
        "srs_bonus": srs,
        "recency_penalty": recency,
        "new_word_count": new_word_count,
        "review_word_count": review_word_count,
    }
