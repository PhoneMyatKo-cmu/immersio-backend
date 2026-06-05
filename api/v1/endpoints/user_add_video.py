from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from db.base import get_db
from schemas.video import VideoUrl
from services.video_submission_service import (
    SubmissionResult,
    submit_video_for_processing,
)

router = APIRouter(prefix="/add-video")


@router.post("/")
def add_video(
    data: VideoUrl, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> SubmissionResult:

    return submit_video_for_processing(data.youtube_url, db, background_tasks)
