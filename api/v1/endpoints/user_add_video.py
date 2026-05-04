from fastapi import APIRouter,HTTPException,Depends
from pydantic import BaseModel
from utils.video_validation_helpers import validate_video
from services.video_services import save_video,check_video_exists,get_video_by_url
from sqlalchemy.ext.asyncio import AsyncSession
from db.base import get_db
from services.caption_services import save_tokenized_captions
from services.vocab_services import save_vocabularies
from utils.captions_helpers import fetch_raw_captions,tokenize_captions
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
    saved_video_db_id=get_video_by_url(video_id,db).id
    
    raw_captions=fetch_raw_captions(video_id)
    tokenized_captions=tokenize_captions(raw_captions)
    caption_len=0
    flattened_token=[t for caption in tokenized_captions for t in caption["tokens"]]
    print(flattened_token[:5])
    try:
        caption_len=save_tokenized_captions(tokenized_captions,saved_video_db_id,db)
    except Exception:
        print("Db error")
    
    
    save_vocabularies(flattened_token,db)
    
    
       
    return {
        "status":"success",
        "error":None,
        "title":video["title"],
        "caption_len":caption_len
    }

    