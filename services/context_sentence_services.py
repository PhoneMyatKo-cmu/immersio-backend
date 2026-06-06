from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.sentence import Sentence
from services.google_translate_service import fall_back_google_translate


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
        "translation": best.translation,
        "start": best.start_time,
        "end": best.end_time,
        "sentence_index": best.sentence_index,
    }


def cache_translation(sentence_id: int, translation: str, db: Session):
    sentence = db.scalars(select(Sentence).where(Sentence.id == sentence_id)).first()
    sentence.translation = translation
    db.add(sentence)
    db.commit()


def get_sentence_translation(context_sentence: dict, db: Session) -> str:

    if context_sentence["translation"]:
        print("Translation cache")
        return context_sentence["translation"]

    else:
        try:
            print("Translation cache miss")
            context_sentence_translation = fall_back_google_translate(
                context_sentence["text"]
            )[0]
            cache_translation(context_sentence["id"], context_sentence_translation, db)
            return context_sentence_translation

        except Exception as e:
            print(e)
            return "Translation service currently unavailable!"


def get_sentence_by_video_id(video_id: int, db: Session):
    results = db.scalars(
        select(Sentence).where(Sentence.video_id == video_id)
    ).fetchall()
    return results
