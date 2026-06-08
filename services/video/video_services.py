import isodate
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from db.base import SessionLocal
from models.video import DifficultyLevel, Video
from services.video_vocab.video_vocab_service import get_video_vocab_with_tiers
from utils.video_validation_helpers import compute_difficulty


def check_video_exists(youtube_video_id: str, db: Session) -> Video | None:
    """Check whether video exists in the database
    Return video if exists, none if doesn't exist
    """

    result = db.scalars(
        select(Video).where(Video.youtube_video_id == youtube_video_id)
    ).first()
    return result


def save_video(meta_data: dict, suitability: dict, db: Session):
    """save video metadata to the database"""

    # duration_funtion to be implemented later
    try:
        video = Video(
            youtube_video_id=meta_data["video_id"],
            title=meta_data["title"],
            thumbnail_url=meta_data["thumbnail_url"],
            channel_name=meta_data["channel_name"],
            duration_seconds=isodate.parse_duration(
                meta_data["duration"]
            ).total_seconds(),
        )
        db.add(video)
        db.commit()
    except Exception as e:
        print(e)
        raise e

    return {"title": meta_data["title"]}


def save_vocabulary_profile():
    pass


def save_difficulty_level():
    pass


def get_video_by_youtube_video_id(youtube_video_id: str, db: Session):
    stmt = select(Video).where(Video.youtube_video_id == youtube_video_id)

    row = db.execute(stmt).scalars().first()
    return row


def get_video_by_id(id: int, db: Session):
    stmt = select(Video).where(Video.id == id)

    row = db.execute(stmt).scalars().first()
    return row


def get_videos_by_difficulty_level(
    difficulty_level: DifficultyLevel,
    db: Session,
    search: str,
    page: int,
    page_size: int,
):
    stmt = (
        select(Video)
        .where(Video.difficulty_level == difficulty_level)
        .order_by(Video.created_at.desc())
    )

    if search:
        stmt = stmt.where(Video.title.ilike(f"%{search}%"))

    rows = (
        db.execute(stmt.limit(page_size).offset((page - 1) * page_size)).scalars().all()
    )

    total_videos = get_total_video_count(db, stmt)
    return rows, total_videos


def get_videos(db: Session, search: str = None, page: int = 1, page_size: int = 6):
    stmt = select(Video).order_by(Video.created_at.desc())

    if search:
        stmt = stmt.where(Video.title.ilike(f"%{search}%"))

    rows = (
        db.execute(stmt.limit(page_size).offset((page - 1) * page_size)).scalars().all()
    )
    total_videos = get_total_video_count(db, stmt)
    return rows, total_videos


def get_total_video_count(db: Session, stmt: select):
    total_videos = db.scalar(select(func.count()).select_from(stmt.subquery()))
    return total_videos


def save_difficulty(video_id: int, db: Session):
    video_vocab_list = get_video_vocab_with_tiers(video_id=video_id, db=db)
    difficulty_level = compute_difficulty(video_vocab=video_vocab_list)

    if difficulty_level == "unknown":
        difficulty_level = DifficultyLevel.beginner
    else:
        difficulty_level = DifficultyLevel(difficulty_level)

    db.execute(
        update(Video)
        .where(Video.id == video_id)
        .values(difficulty_level=difficulty_level)
    )
    db.commit()


def change_shadowing_status(video_id: int, db: Session) -> None:
    """Set is_shadowing_ready to True by video ID."""
    db.execute(
        update(Video).where(Video.id == video_id).values(is_shadowing_ready=True)
    )
    db.commit()
