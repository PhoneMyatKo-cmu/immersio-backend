# services/shadowing_sentence_background_service.py

import logging

from db.base import SessionLocal
from services.context_sentence_services import save_context_sentence
from services.video_services import change_shadowing_status
from services.yt_whisper import youtube_to_sentences

logger = logging.getLogger(__name__)


def build_shadowing_sentences_with_whisper_background_task(
    youtube_video_id: str, video_id: int
):
    logger.info(f"[shadowing] START video_id={video_id}, youtube_id={youtube_video_id}")
    db = SessionLocal()

    try:
        logger.info(f"[shadowing] video_id={video_id} - Starting transcription...")
        sentences = youtube_to_sentences(youtube_video_id, shadow=True)

        if not sentences:
            logger.warning(
                f"[shadowing] video_id={video_id} - No sentences generated, skipping"
            )
            return

        logger.info(
            f"[shadowing] video_id={video_id} - Generated {len(sentences)} sentences"
        )

        logger.info(f"[shadowing] video_id={video_id} - Saving sentences to DB...")
        save_context_sentence(sentences, video_id, db)

        logger.info(f"[shadowing] video_id={video_id} - Marking as shadowing ready...")
        change_shadowing_status(video_id, db)

        db.commit()
        logger.info(f"[shadowing] SUCCESS video_id={video_id}")

    except Exception as e:
        db.rollback()
        logger.error(f"[shadowing] FAILED video_id={video_id}: {e}", exc_info=True)

    finally:
        db.close()
        logger.info(f"[shadowing] END video_id={video_id}")
