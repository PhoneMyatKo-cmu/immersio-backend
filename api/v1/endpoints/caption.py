from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from db.base import get_db
from models.processed_caption import ProcessedCaption
from services.caption_services import get_captions_by_video_id

router = APIRouter(prefix="/get-caption")


class CaptionListResponse(BaseModel):
    id: int
    caption_index: int
    text: str
    tokens: list
    start_time: float
    end_time: float
    duration: float

    model_config = ConfigDict(from_attributes=True)


@router.get("/by-video-id")
def get_captions_by_video(
    video_id: int, db: Session = Depends(get_db)
) -> list[CaptionListResponse]:
    print(video_id)

    captionList = get_captions_by_video_id(video_id, db)
    return captionList
