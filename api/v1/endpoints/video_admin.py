from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from db.base import get_db
from models.user import User
from models.video import VideoSource
from schemas.video import VideoUrl
from services.auth.authentication_service import require_admin
from services.video.video_submission_service import (
    SubmissionResult,
    submit_video_for_processing,
)

router = APIRouter(prefix="/admin/videos", tags=["admin-videos"])


@router.post("/")
def add_video(
    data: VideoUrl,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> SubmissionResult:
    return submit_video_for_processing(
        data.youtube_url,
        db,
        background_tasks,
        source=VideoSource.curated,
        added_by=admin.id,
    )
