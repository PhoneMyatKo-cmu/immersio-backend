import logging

from db.base import SessionLocal
from services.video_services import save_difficulty
from services.video_vocab_service import save_video_vocab_profile

logger = logging.getLogger(__name__)


def process_video_vocab_background(video_id: int, surface_forms: list[str]) -> None:
    db = SessionLocal()

    logger.info(
        "Starting video vocab background processing",
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

        save_difficulty(
            video_id=video_id,
            db=db,
        )

        logger.info(
            "Finished video vocab background processing",
            extra={
                "video_id": video_id,
                "surface_form_count": len(surface_forms),
            },
        )

    except Exception:
        db.rollback()
        logger.exception(
            "Failed video vocab background processing",
            extra={
                "video_id": video_id,
                "surface_form_count": len(surface_forms),
            },
        )

    finally:
        db.close()
