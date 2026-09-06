from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.base import get_db
from schemas.recommendation import (
    RecommendationFeed,
    RecommendationResponse,
    RecommendedVideo,
)
from schemas.video import VideoResponse
from services.auth.authentication_service import get_current_user
from services.recommendation.recommendation_service import get_recommended_videos
from services.video.video_services import (
    get_video_by_id,
    get_videos,
)

router = APIRouter(prefix="/video")


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


# @router.get("/difficulty/{difficulty_level}")
# def get_videos_by_difficulty(
#     db: Session = Depends(get_db),
#     difficulty_level: DifficultyLevel = DifficultyLevel.beginner,
#     search: str = None,
#     page: int = 1,
#     page_size: int = 6,
# ):
#     videos, total_videos = get_videos_by_difficulty_level(
#         difficulty_level, db, search, page, page_size
#     )
#     total_pages = (total_videos + page_size - 1) // page_size
#     return videos, total_pages


@router.get("/recommendation", response_model=RecommendationFeed)
def recommend_videos(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    page: int = 1,
    page_size: int = 6,
):

    return get_recommended_videos(current_user, db, page, page_size)


@router.get("/{id}")
def get_video(id: int, db: Session = Depends(get_db)) -> VideoResponse:

    video = get_video_by_id(id, db)
    if video is not None:
        return video
    raise HTTPException(status_code=404, detail="Video not found.")


@router.get("/{video_id}/shadowing-status")
def shadowing_status(video_id: int, db: Session = Depends(get_db)):
    video = get_video_by_id(video_id, db)
    if not video:
        raise HTTPException(404, "Video not found")
    return {"is_shadowing_ready": video.is_shadowing_ready}
