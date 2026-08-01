import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.video_vocab_profile import VideoVocabulary
from models.vocab import Vocabulary

logger = logging.getLogger(__name__)


def save_video_vocab_profile(
    video_id: int, surface_forms: list[str], vocab_caption_map: dict[str, list[int]], db: Session
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

    existing_rows = (
        db.query(VideoVocabulary)
        .filter(VideoVocabulary.video_id == video_id)
        .filter(VideoVocabulary.vocab_id.in_(form_to_id.values()))
        .all()
    )
    existing_map = {row.vocab_id: row for row in existing_rows}

    for form, frequency in freq_map.items():
        vocab_id = form_to_id.get(form)
        if not vocab_id:
            continue  # word not in global vocab — skip

        existing = existing_map.get(vocab_id)
        if existing:
            existing.frequency += frequency
        else:
            row = VideoVocabulary(video_id=video_id, vocab_id=vocab_id, frequency=frequency)
            db.add(row)
            existing_map[vocab_id] = row  # Add to existing_map for caption_indices update

    for form, caption_indices in vocab_caption_map.items():
        vocab_id = form_to_id.get(form)
        if not vocab_id:
            continue  # word not in global vocab — skip

        existing = existing_map.get(vocab_id)
        
        caption_indices_str = ",".join(map(str, caption_indices))

        if existing:
            existing.caption_indices = (
                existing.caption_indices + "," + caption_indices_str
                if existing.caption_indices
                else caption_indices_str
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
