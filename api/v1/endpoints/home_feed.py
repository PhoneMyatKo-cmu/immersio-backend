from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.base import get_db
from services.video_services import get_all_videos, get_videos_by_difficulty_level

router = APIRouter(prefix="/feed")

@router.get("/")
def get_home_feed(db: Session = Depends(get_db)):
    videos = get_all_videos(db)
    return videos

@router.get("/difficulty/{difficulty_level}")
def get_videos_by_difficulty(difficulty_level: str, db: Session = Depends(get_db)):
    videos = get_videos_by_difficulty_level(difficulty_level, db)
    return videos
