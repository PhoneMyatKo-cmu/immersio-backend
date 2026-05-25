from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.sentence import Sentence


def save_context_sentence(sentences: list, video_db_id: int, db: Session):
    for st in sentences:
        sentence = Sentence(
            video_id=video_db_id,
            sentence_index=st["sentence_index"],
            text=st["text"],
            start_time=st["start"],
            end_time=st["end"],
            duration=st["duration"],
        )
        db.add(sentence)
    number_of_sentences = len(sentences)
    db.commit()
    return {"number_of_sentences": number_of_sentences}


def find_context_sentence(
    word: str,
    video_id: str,
    timestamp: float,
    db: Session,
    time_window: float = 3.0,  # search within ±3 seconds
) -> Optional[dict]:
    """
    Find the reconstructed sentence that contains this word
    at approximately this timestamp.
    """
    candidates = (
        db.query(Sentence)
        .filter(
            Sentence.video_id == video_id,
            Sentence.start_time <= timestamp,
            Sentence.end_time >= timestamp,
            Sentence.text.contains(word),
        )
        .all()
    )

    if not candidates:
        # Widen search: maybe timing is off, just find by text
        candidates = (
            db.query(Sentence)
            .filter(
                Sentence.video_id == video_id,
                Sentence.text.contains(word),
            )
            .order_by(
                # Closest to the timestamp
                func.abs(Sentence.start_time - timestamp)
            )
            .limit(3)
            .all()
        )

    if not candidates:
        return None

    # Pick the best match: closest timestamp that contains the word
    best = min(candidates, key=lambda s: abs(s.start_time - timestamp))

    return {
        "id": best.id,
        "text": best.text,
        "start": best.start_time,
        "end": best.end_time,
        "sentence_index": best.sentence_index,
    }
