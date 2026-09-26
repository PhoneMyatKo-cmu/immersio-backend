"""Seed a demo learner profile for the recommendation feature.

Instead of guessing a video's intrinsic difficulty, this engineers each target
video's *coverage* for one demo user: it marks the video's highest-frequency
words KNOWN until their cumulative frequency reaches a target, so the video lands
in the difficulty bucket you choose. Coverage is frequency-weighted, so ordering
by frequency and stopping at the target hits that coverage precisely.

It also seeds one SRS *due* word (a "review words" badge on one video) and one
recent watch (to demonstrate the recency filter).

Usage:
    1. Fill in USER_ID and the real video ids from your ingested catalog below.
    2. python scripts/seed_demo.py
    3. Call GET /video/recommendation as that user and confirm each video's
       understand_percent matches its target. If a video set to 0.90 shows ~30%,
       that's the vocab_id key-mismatch bug (fix the int coercion), not the seed.

Re-runnable: it clears the demo user's exposure / saved-vocab / session rows
first, so running it repeatedly does not stack duplicates.
"""

import os
import sys
import uuid
from datetime import datetime, timedelta

# Allow running as a standalone script (python scripts/seed_demo.py) by putting
# the project root on the import path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.base import SessionLocal  # noqa: E402
from models.learning_session import LearningSession  # noqa: E402

# Imported so SQLAlchemy can resolve the string relationships referenced by the
# models above (LearningSession -> User/Video, Video -> Caption/ShadowingSentence).
from models.processed_caption import Caption  # noqa: E402, F401
from models.sentence import ShadowingSentence  # noqa: E402, F401
from models.user import User  # noqa: E402, F401
from models.user_vocab_library import SRSState, UserSavedVocabulary  # noqa: E402
from models.user_vocab_profile import UserVocabularyExposure, VocabStatus  # noqa: E402
from models.video import Video  # noqa: E402, F401
from models.video_vocab_profile import VideoVocabulary  # noqa: E402
from models.vocab import Vocabulary  # noqa: E402

# ------------------------------------------------------------------ #
# Configure these for your demo account and catalog
# ------------------------------------------------------------------ #
USER_ID = 5

# video_id -> target coverage. Drives that video's difficulty bucket for USER_ID:
#   >= 0.95 comfortable | 0.85-0.95 best_fit | 0.70-0.85 stretch | < 0.70 too_advanced
COVERAGE_TARGETS = {
    10: 0.96,  # -> "Easy For You"
    11: 0.70,  # -> "Just Right"
    12: 0.80,  # -> "Challenge"
    9: 0.50,  # -> stays too_advanced (not surfaced)
}
SRS_VIDEO_ID = 11  # a surfaced video that will show a "review words" badge
WATCHED_VIDEO_ID = 12  # marked just-watched -> excluded by the recency filter
MIN_PROFILE = 0  # pad known words up to this many so we stay out of cold start
# ------------------------------------------------------------------ #


def clear_demo_data(db) -> None:
    db.query(UserVocabularyExposure).filter_by(user_id=USER_ID).delete()
    db.query(UserSavedVocabulary).filter_by(user_id=USER_ID).delete()
    db.query(LearningSession).filter_by(user_id=USER_ID).delete()
    db.commit()


def _mark_known(db, vocab_id, marked: set) -> None:
    if vocab_id in marked:
        return
    db.add(
        UserVocabularyExposure(
            user_id=USER_ID,
            vocab_id=vocab_id,
            seen_count=50,
            status=VocabStatus.know,
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
    )
    marked.add(vocab_id)


def set_coverage(db, video_id: int, target: float, marked: set) -> None:
    """Mark the video's top-frequency words KNOWN until coverage ~= target."""
    rows = (
        db.query(VideoVocabulary)
        .filter_by(video_id=video_id)
        .order_by(VideoVocabulary.frequency.desc())
        .all()
    )
    total = sum(r.frequency for r in rows) or 1
    acc = 0
    for r in rows:
        if acc / total >= target:
            break
        _mark_known(db, r.vocab_id, marked)
        acc += r.frequency


def pad_profile(db, marked, minimum, target_video_ids):
    if len(marked) >= minimum:
        return
    # words that appear in any target video -> unsafe as filler (they'd inflate coverage)
    target_vocab = {
        vid
        for (vid,) in db.query(VideoVocabulary.vocab_id)
        .filter(VideoVocabulary.video_id.in_(target_video_ids))
        .all()
    }
    need = minimum - len(marked)
    extra = (
        db.query(Vocabulary.id)
        .filter(~Vocabulary.id.in_(list(marked | target_vocab) or [0]))
        .limit(need)
        .all()
    )
    for (vid,) in extra:
        _mark_known(db, vid, marked)


def main() -> None:
    db = SessionLocal()
    try:
        clear_demo_data(db)
        marked: set = set()

        for video_id, target in COVERAGE_TARGETS.items():
            set_coverage(db, video_id, target, marked)
        pad_profile(db, marked, MIN_PROFILE, list(COVERAGE_TARGETS.keys()))

        # SRS: one due studying word inside SRS_VIDEO_ID -> review badge + boost.
        srs_word = db.query(VideoVocabulary).filter_by(video_id=SRS_VIDEO_ID).first()
        if srs_word:
            db.add(
                UserSavedVocabulary(
                    user_id=USER_ID,
                    vocab_id=srs_word.vocab_id,
                    video_id=SRS_VIDEO_ID,
                    srs_state=SRSState.studying,
                    interval_days=3,
                    next_review_date=datetime.utcnow() - timedelta(days=1),
                )
            )

        # Recency: mark WATCHED_VIDEO_ID as just watched -> drops out of the feed.
        db.add(
            LearningSession(
                id=uuid.uuid4().hex,
                user_id=USER_ID,
                video_id=WATCHED_VIDEO_ID,
                start_time=datetime.utcnow() - timedelta(minutes=10),
                end_time=datetime.utcnow(),
            )
        )

        db.commit()
        print(
            f"Seeded demo profile for user {USER_ID}: "
            f"{len(marked)} known words across {len(COVERAGE_TARGETS)} videos; "
            f"SRS due word on video {SRS_VIDEO_ID}; "
            f"recent watch on video {WATCHED_VIDEO_ID}."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
