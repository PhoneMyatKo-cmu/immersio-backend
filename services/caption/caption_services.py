from sqlalchemy import select
from sqlalchemy.orm import Session

from db.base import get_db
from models.processed_caption import ProcessedCaption
from services.external.google_translate_service import google_translate


def save_tokenized_captions(tokenized_captions: list[dict], video_id: int, db: Session):
    try:
        for caption in tokenized_captions:
            tokenized_caption = ProcessedCaption(
                video_id=video_id,
                caption_index=caption["index"],
                tokens=caption["tokens"],
                start_time=caption["start"],
                end_time=float(caption["start"]) + float(caption["duration"]),
                duration=caption["duration"],
                text=caption["text"],
            )

            db.add(tokenized_caption)
        db.commit()
    except Exception as e:
        db.rollback()
        print(e)
        raise e

    return len(tokenized_captions)


def get_captions_by_video_id(video_id: int, db: Session):
    captions = []
    try:
        stmt = select(ProcessedCaption).where(ProcessedCaption.video_id == video_id)
        captions = db.execute(stmt).scalars().all()
    except Exception as e:
        print("DB error")
        raise e
    return captions


def cache_translation(caption_id: int, translation: str, db: Session):
    caption = db.scalars(
        select(ProcessedCaption).where(ProcessedCaption.id == caption_id)
    ).first()
    caption.translation = translation
    db.add(caption)
    db.commit()


def get_sentence_translation(context_sentence: dict, db: Session) -> str:

    caption_translation = get_caption_translation(context_sentence["id"], db)
    if caption_translation:
        print("Translation cache")
        return caption_translation

    else:
        try:
            print("Translation cache miss")
            context_sentence_translation = google_translate(
                context_sentence["text"]
            )[0]
            cache_translation(context_sentence["id"], context_sentence_translation, db)
            return context_sentence_translation

        except Exception as e:
            print(e)
            return "Translation service currently unavailable!"


def get_caption_translation(caption_id: int, db: Session):
    caption = db.scalars(
        select(ProcessedCaption).where(ProcessedCaption.id == caption_id)
    ).first()
    return caption.translation
