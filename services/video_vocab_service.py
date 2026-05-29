import logging

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from db.base import SessionLocal
from models.video_vocab_profile import VideoVocabProfile
from models.vocab import Vocabulary

logger = logging.getLogger(__name__)


def save_video_vocab_profile(
    video_id: int, surface_forms: list[str], db: Session
) -> None:
    """
    Save vocabulary profile for a video.
    Takes list of surface forms (including duplicates from captions).
    Groups by vocab_id, counts frequency, upserts to table.
    """
    freq_map: dict[str, int] = {}
    for form in surface_forms:
        freq_map[form] = freq_map.get(form, 0) + 1

    unique_forms = list(freq_map.keys())
    vocab_rows = db.execute(
        select(Vocabulary.id, Vocabulary.japanese_form).where(
            Vocabulary.japanese_form.in_(unique_forms)
        )
    ).fetchall()

    form_to_id = {row.japanese_form: row.id for row in vocab_rows}

    for form, frequency in freq_map.items():
        vocab_id = form_to_id.get(form)
        if not vocab_id:
            continue  # word not in global vocab — skip

        existing = (
            db.query(VideoVocabProfile)
            .filter_by(video_id=video_id, vocab_id=vocab_id)
            .first()
        )

        if existing:
            existing.frequency += frequency
        else:
            db.add(
                VideoVocabProfile(
                    video_id=video_id, vocab_id=vocab_id, frequency=frequency
                )
            )

    db.commit()


def save_video_vocab_profile_background(
    video_id: int, surface_forms: list[str]
) -> None:
    db = SessionLocal()
    logger.info(
        "Starting video vocab profile background task",
        extra={
            "video_id": video_id,
            "surface_form_count": len(surface_forms),
        },
    )
    try:
        save_video_vocab_profile(
            video_id=video_id,
            surface_forms=surface_forms,
            db=db,
        )
        logger.info(
            "Finished video vocab profile background task",
            extra={
                "video_id": video_id,
                "surface_form_count": len(surface_forms),
            },
        )
    except Exception as e:
        db.rollback()
        logger.exception(
            "Failed video vocab profile background task",
            extra={
                "video_id": video_id,
                "surface_form_count": len(surface_forms),
            },
        )
    finally:
        db.close()
