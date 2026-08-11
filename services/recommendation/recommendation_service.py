from sqlalchemy.orm import Session

from schemas.recommendation import RecommendationResponse, RecommendedVideo
from schemas.user import UserRead
from services.user_vocab.user_vocab_service import get_user_saved_vocab
from services.user_vocab_exposure.user_vocab_exposure_service import (
    get_vocab_exposure_by_user,
)
from services.video.video_services import get_videos
from utils.recommendation_helpers import compute_known_weight


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
