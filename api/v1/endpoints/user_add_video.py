from fastapi import APIRouter
from pydantic import BaseModel
from utils.helpers import validate_video

router=APIRouter(prefix="/add-video")

class VideoUrl(BaseModel):
    youtube_url:str

@router.post("/")
async def add_video(data:VideoUrl):
    validation_result=await validate_video(data.youtube_url)
       
    return {
        "url":data.youtube_url,
        "message":validation_result
    }

    