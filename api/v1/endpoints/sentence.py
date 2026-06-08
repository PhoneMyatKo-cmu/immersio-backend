from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from db.base import get_db
from services.sentence.sentence_services import get_sentence_by_video_id

router = APIRouter(prefix="/sentence")


class SentenceListResponse(BaseModel):
    sentence_index: int
    text: str
    # tokens:list
    start_time: float
    end_time: float
    duration: float
    translation: str | None
    model_config = ConfigDict(from_attributes=True)


@router.get("/")
def get_captions_by_video(
    video_id: int, db: Session = Depends(get_db)
) -> list[SentenceListResponse]:
    print(video_id)

    sentenceList = get_sentence_by_video_id(video_id, db)
    return sentenceList
