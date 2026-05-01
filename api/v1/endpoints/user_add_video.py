from fastapi import APIRouter,HTTPException,Depends
from pydantic import BaseModel
from utils.video_validation_helpers import validate_video
from services.video_services import save_video,check_video_exists
from sqlalchemy.ext.asyncio import AsyncSession
from db.base import get_db

router=APIRouter(prefix="/add-video")

class VideoUrl(BaseModel):
    youtube_url:str

@router.post("/")
async def add_video(data:VideoUrl,
                    db:AsyncSession=Depends(get_db)):
    validation_result=await validate_video(data.youtube_url)
    if not validation_result["valid"]:
        return {
            "status":"fail",
            "error":validation_result["error"]
            
            
        }
    video_id=validation_result["video_id"]
    is_video_existing=await check_video_exists(video_id,db)
    if is_video_existing:
        return {
            "status":"fail",
            "error": "Already exists"
        }
    
    video = await save_video(
        meta_data=validation_result["meta_data"],
        suitability=validation_result["suitablity"],
        db=db
    )
    
       
    return {
        "status":"success",
        "error":None,
        "title":video["title"]
    }

    