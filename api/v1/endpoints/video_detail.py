from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.base import get_db
from schemas.video import VideoRespone
from services.video_services import get_video_by_id

router = APIRouter(prefix="/video")


@router.get("/get-by-id")
def get_video(id: int, db: Session = Depends(get_db)) -> VideoRespone:

    video = get_video_by_id(id, db)
    if video is not None:
        return video
    raise HTTPException(status_code=404, detail="Video not found.")
