from datetime import datetime

from sqlalchemy.orm import Session

from models.learning_session import LearningSession
from models.session_vocab import SessionVocabulary
from models.user_vocab_profile import UserVocabularyExposure
from schemas.session import SessionData
from services.session.session_service import get_learning_sessions_by_user_and_video
from services.session_vocab.session_vocab_service import get_session_vocab_batch
from services.video.video_services import get_video_by_id
from utils.user_vocab_exposure_helper import isIntervalOverlapping


def get_user_vocab_exposure(user_id: int, db: Session):
    """
    Retrieve user vocabulary exposure data for a specific user and video.
    """
    return (
        db.query(UserVocabularyExposure)
        .filter(UserVocabularyExposure.user_id == user_id)
        .all()
    )


def save_user_vocab_exposure(session_data: LearningSession, db: Session):
    intervals = session_data.video_intervals
    user_id = session_data.user_id
    video_id = session_data.video_id
    now = session_data.end_time  # Use the end_time of the session as the current time

    # Fetch existing exposures and sessions for the user and video
    existing_exposures = get_user_vocab_exposure(user_id, db)
    existing_sessions = get_learning_sessions_by_user_and_video(user_id, video_id, db)
    existing_session_vocabs = get_session_vocab_batch(
        [session.id for session in existing_sessions], db
    )

    video = get_video_by_id(video_id, db)
    if not video:
        raise ValueError(f"Video with id {video_id} not found.")

    video_vocab_profiles = video.vocabulary_entries

    captions = video.captions

    # Process each vocabulary profile and check for exposure within the session intervals
    for vocab_profile in video_vocab_profiles:
        if any(sv.vocab_id == vocab_profile.id for sv in existing_session_vocabs):
            print(
                f"Vocabulary {vocab_profile.vocab_id} already recorded for this session. Skipping."
            )
            continue  # Skip if the vocabulary exposure has already been recorded for this session
        isRecorded = False  # Flag to check if the vocabulary exposure has been recorded for this session
        caption_indices = (
            vocab_profile.caption_indices.split(",")
            if vocab_profile.caption_indices
            else []
        )
        for index_str in caption_indices:
            try:
                index = int(index_str)
            except ValueError:
                continue  # Skip invalid indices

            if 0 <= index < len(captions):
                caption = next((c for c in captions if c.caption_index == index), None)
                if not caption:
                    raise ValueError(
                        f"Caption with index {index} not found for video {video_id}."
                    )

                for interval in intervals:
                    start_time = interval.start_time
                    end_time = interval.end_time

                    if isIntervalOverlapping(
                        caption.start_time, caption.end_time, start_time, end_time
                    ):
                        vocab_exposure = next(
                            (
                                (
                                    exposure
                                    for exposure in existing_exposures
                                    if exposure.vocab_id == vocab_profile.vocab_id
                                )
                            ),
                            None,
                        )
                        if vocab_exposure:
                            vocab_exposure.seen_count += 1
                            if vocab_exposure.last_seen_at < now:
                                vocab_exposure.last_seen_at = now
                            if vocab_exposure.seen_count > 10:
                                vocab_exposure.status = "KNOW"
                        else:
                            new_exposure = UserVocabularyExposure(
                                user_id=user_id,
                                vocab_id=vocab_profile.vocab_id,
                                seen_count=1,
                                status="SEEN",
                                first_seen_at=now,
                                last_seen_at=now,
                            )
                            db.add(new_exposure)
                            existing_exposures.append(new_exposure)
                        new_session_vocab = SessionVocabulary(
                            session_id=session_data.id, vocab_id=vocab_profile.id
                        )
                        db.add(new_session_vocab)
                        isRecorded = True
                        break  # Add only once vocabulary exposure per session, even if it appears in multiple captions within the interval
            if isRecorded:
                break

    db.commit()


def get_vocab_seen_by_user(user_id: int, db: Session):
    """
    Retrieve all vocabulary seen by a specific user.
    """
    return (
        db.query(UserVocabularyExposure)
        .filter(UserVocabularyExposure.user_id == user_id)
        .all()
    )


def get_vocab_known_by_user(user_id: int, db: Session):
    """
    Retrieve all vocabulary known by a specific user.
    """
    return (
        db.query(UserVocabularyExposure)
        .filter(
            UserVocabularyExposure.user_id == user_id,
            UserVocabularyExposure.status == "KNOW",
        )
        .all()
    )


def get_vocab_exposure_by_user(user_id: int, db: Session):
    """
    Retrieve all exposed vocabulary by a specific user.
    """
    return (
        db.query(UserVocabularyExposure)
        .filter(UserVocabularyExposure.user_id == user_id)
        .all()
    )
