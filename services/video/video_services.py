from datetime import datetime, timedelta

import isodate
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from models.user import User
from models.video import Video, VideoSource


def check_video_exists(youtube_video_id: str, db: Session) -> Video | None:
    """Check whether video exists in the database
    Return video if exists, none if doesn't exist
    """

    result = db.scalars(
        select(Video).where(Video.youtube_video_id == youtube_video_id)
    ).first()
    return result


def save_video(
    meta_data: dict,
    suitability: dict,
    db: Session,
    source: VideoSource = VideoSource.user_submitted,
    added_by: int | None = None,
):
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
            source=source,
            added_by=added_by,
        )
        db.add(video)
        db.flush()
        video_id = video.id
        db.commit()

    except Exception as e:
        print(e)
        raise e

    return {"title": meta_data["title"], "video_id": video_id}


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


# def get_videos_by_difficulty_level(
#     difficulty_level: DifficultyLevel,
#     db: Session,
#     search: str,
#     page: int,
#     page_size: int,
# ):
#     stmt = (
#         select(Video)
#         .where(Video.difficulty_level == difficulty_level)
#         .order_by(Video.created_at.desc())
#     )

#     if search:
#         stmt = stmt.where(Video.title.ilike(f"%{search}%"))

#     rows = (
#         db.execute(stmt.limit(page_size).offset((page - 1) * page_size)).scalars().all()
#     )

#     total_videos = get_total_video_count(db, stmt)
#     return rows, total_videos


def get_videos(db: Session, search: str = None, page: int = 1, page_size: int = 6):
    stmt = (
        select(Video).where(Video.is_active.is_(True)).order_by(Video.created_at.desc())
    )

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


def get_videos_admin(
    db: Session,
    search: str = None,
    source: VideoSource | None = None,
    is_active: bool | None = None,
    added_by: int | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """List videos for admin with optional filters.

    Unlike get_videos, this does not hide inactive videos by default; each
    filter is applied only when provided (None = don't filter on that axis).
    Returns (rows, total_count).
    """
    stmt = select(Video).order_by(Video.created_at.desc())

    if search:
        stmt = stmt.where(Video.title.ilike(f"%{search}%"))
    if source is not None:
        stmt = stmt.where(Video.source == source)
    if is_active is not None:
        stmt = stmt.where(Video.is_active.is_(is_active))
    if added_by is not None:
        stmt = stmt.where(Video.added_by == added_by)

    rows = (
        db.execute(stmt.limit(page_size).offset((page - 1) * page_size)).scalars().all()
    )
    total_videos = get_total_video_count(db, stmt)
    return rows, total_videos


# def save_difficulty(video_id: int, db: Session):
#     video_vocab_list = get_video_vocab_with_tiers(video_id=video_id, db=db)
#     difficulty_level = compute_difficulty(video_vocab=video_vocab_list)

#     if difficulty_level == "unknown":
#         difficulty_level = DifficultyLevel.beginner
#     else:
#         difficulty_level = DifficultyLevel(difficulty_level)

#     db.execute(
#         update(Video)
#         .where(Video.id == video_id)
#         .values(difficulty_level=difficulty_level)
#     )
#     db.commit()


def change_shadowing_status(video_id: int, db: Session) -> None:
    """Set is_shadowing_ready to True by video ID."""
    db.execute(
        update(Video).where(Video.id == video_id).values(is_shadowing_ready=True)
    )
    db.commit()


def get_video_stats(db: Session, top_contributors_limit: int = 5) -> dict:
    """Aggregate platform-wide video catalog stats for the admin dashboard."""
    now = datetime.utcnow()

    total = db.scalar(select(func.count()).select_from(Video)) or 0
    active = (
        db.scalar(
            select(func.count()).select_from(Video).where(Video.is_active.is_(True))
        )
        or 0
    )

    source_rows = db.execute(
        select(Video.source, func.count()).group_by(Video.source)
    ).all()
    source_counts = {source: count for source, count in source_rows}

    ready = (
        db.scalar(
            select(func.count())
            .select_from(Video)
            .where(Video.is_shadowing_ready.is_(True))
        )
        or 0
    )

    last_7 = (
        db.scalar(
            select(func.count())
            .select_from(Video)
            .where(Video.created_at >= now - timedelta(days=7))
        )
        or 0
    )
    last_30 = (
        db.scalar(
            select(func.count())
            .select_from(Video)
            .where(Video.created_at >= now - timedelta(days=30))
        )
        or 0
    )

    # contributor_rows = db.execute(
    #     select(
    #         Video.added_by,
    #         func.concat(User.first_name, " ", User.last_name),
    #         func.count(),
    #     )
    #     .join(User, User.id == Video.added_by)
    #     .where(Video.added_by.is_not(None))
    #     .group_by(Video.added_by, User.first_name, User.last_name)
    #     .order_by(func.count().desc())
    #     .limit(top_contributors_limit)
    # ).all()

    return {
        "total": total,
        "active": active,
        "inactive": total - active,
        "by_source": {
            "curated": source_counts.get(VideoSource.curated, 0),
            "user_submitted": source_counts.get(VideoSource.user_submitted, 0),
        },
        "shadowing_ready": ready,
        "shadowing_not_ready": total - ready,
        "added_last_7_days": last_7,
        "added_last_30_days": last_30,
        # "top_contributors": [
        #     {"added_by": added_by, "name": name, "count": count}
        #     for added_by, name, count in contributor_rows
        # ],
    }


def soft_delete_video(video_id: int, db: Session) -> Video | None:
    """Soft-delete a video by setting is_active to False.

    Returns the updated video, or None if no video with that id exists.
    """
    video = get_video_by_id(video_id, db)
    if video is None:
        return None

    video.is_active = False
    db.commit()
    db.refresh(video)
    return video


def get_youtube_video_id_by_video_id(video_id: int, db: Session) -> str | None:
    """Get youtube_video_id by video ID."""
    result = db.scalars(
        select(Video.youtube_video_id).where(Video.id == video_id)
    ).first()
    return result
