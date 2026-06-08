from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.base import get_db
from models.video import DifficultyLevel
from services.video.video_services import get_videos, get_videos_by_difficulty_level

router = APIRouter(prefix="/feed")


@router.get("/")
def get_home_feed(
    db: Session = Depends(get_db), search: str = None, page: int = 1, page_size: int = 6
):
    videos, total_videos = get_videos(
        db, search=search.lower() if search else None, page=page, page_size=page_size
    )
    total_pages = (total_videos + page_size - 1) // page_size
    print(f"Total videos: {total_videos}, Total pages: {total_pages}")
    return videos, total_pages


@router.get("/difficulty/{difficulty_level}")
def get_videos_by_difficulty(
    db: Session = Depends(get_db),
    difficulty_level: DifficultyLevel = DifficultyLevel.beginner,
    search: str = None,
    page: int = 1,
    page_size: int = 6,
):
    videos, total_videos = get_videos_by_difficulty_level(
        difficulty_level, db, search, page, page_size
    )
    total_pages = (total_videos + page_size - 1) // page_size
    return videos, total_pages
