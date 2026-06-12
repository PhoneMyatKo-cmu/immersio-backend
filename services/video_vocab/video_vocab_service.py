import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.video_vocab_profile import VideoVocabulary
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
            db.query(VideoVocabulary)
            .filter_by(video_id=video_id, vocab_id=vocab_id)
            .first()
        )

        if existing:
            existing.frequency += frequency
        else:
            db.add(
                VideoVocabulary(
                    video_id=video_id, vocab_id=vocab_id, frequency=frequency
                )
            )

    db.commit()


def get_video_vocab_with_tiers(video_id: int, db: Session) -> list[dict]:
    rows = db.execute(
        select(
            Vocabulary.japanese_form,
            Vocabulary.estimated_level,
            VideoVocabulary.frequency,
        )
        .join(VideoVocabulary, VideoVocabulary.vocab_id == Vocabulary.id)
        .where(VideoVocabulary.video_id == video_id)
    ).all()

    return [
        {
            "base_form": row.japanese_form,
            "jlpt_tier": row.estimated_level.value,
            "frequency": row.frequency,
        }
        for row in rows
    ]
