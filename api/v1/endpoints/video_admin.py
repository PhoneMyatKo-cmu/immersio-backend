from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.base import get_db
from models.user import User
from models.video import VideoSource
from math import ceil
from schemas.user import Message
from schemas.video import VideoAdminListResponse, VideoUrl
from services.auth.authentication_service import require_admin
from services.video.video_services import get_videos_admin, soft_delete_video
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


@router.get("/")
def list_videos(
    search: str = None,
    source: VideoSource | None = None,
    is_active: bool | None = None,
    added_by: int | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> VideoAdminListResponse:
    videos, total = get_videos_admin(
        db,
        search=search.lower() if search else None,
        source=source,
        is_active=is_active,
        added_by=added_by,
        page=page,
        page_size=page_size,
    )
    return VideoAdminListResponse(
        items=videos,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if page_size else 0,
    )


@router.delete("/{video_id}")
def remove_video(
    video_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Message:
    video = soft_delete_video(video_id, db)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Video not found"
        )
    return Message(detail="Video removed successfully")
