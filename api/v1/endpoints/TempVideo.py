from fastapi import APIRouter,HTTPException,Depends
from pydantic import BaseModel, ConfigDict
from db.base import get_db
from sqlalchemy.orm import Session
from services.video_services import get_video_by_id
router=APIRouter(prefix="/video")

class VideoRespone(BaseModel):
    youtube_video_id:str
    title:str
    thumbnail_url:str
    channel_name:str
    duration_seconds:int
    
    model_config=ConfigDict(from_attributes=True)

@router.get("/get-by-id")
def get_video(id:int,db:Session=Depends(get_db))->VideoRespone:
    video=get_video_by_id(id,db)
    return video
