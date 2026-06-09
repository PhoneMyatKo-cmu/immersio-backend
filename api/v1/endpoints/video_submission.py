from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.base import get_db
from schemas.video import VideoUrl
from services.auth.authentication_service import get_current_user
from services.video.video_submission_service import (
    SubmissionResult,
    submit_video_for_processing,
)

router = APIRouter(prefix="/submit-video")


@router.post("/")
def add_video(
    data: VideoUrl,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SubmissionResult:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthenticated"
        )
    return submit_video_for_processing(data.youtube_url, db, background_tasks)
