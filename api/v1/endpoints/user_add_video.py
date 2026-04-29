from fastapi import APIRouter
from pydantic import BaseModel

router=APIRouter(prefix="/add-video")

class VideoUrl(BaseModel):
    youtube_url:str

@router.post("/")
def add_video(data:VideoUrl):
    return {
        "url":data.youtube_url,
        "status":"success"
    }

    