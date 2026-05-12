from sqlalchemy import text
from models.video import Video
from sqlalchemy.orm import Session
from sqlalchemy import select

def check_video_exists(youtube_video_id:str,
                             db:Session)->bool:
    
    """ Check whether video exists in the database"""
    # result=db.execute(
    #                     text("SELECT id FROM videos WHERE url = :vid"),
    #                     {"vid":youtube_video_id}
    #                 )
    result=db.scalars(
        select(Video).where(Video.youtube_video_id==youtube_video_id)).first()
    

    return result is not None


def save_video(meta_data:dict , suitability : dict, db:Session ):
    """ save video metadata to the database"""
    
    # duration_funtion to be implemented later
    video=Video(
        youtube_video_id=meta_data["video_id"],
        title=meta_data["title"],
        thumbnail_url=meta_data["thumbnail_url"],
        channel_name=meta_data["channel_name"],
        duration_seconds=100,
    )
    db.add(video)
    db.commit()
    
    return{
        "title":meta_data["title"]
    }
    

def save_vocabulary_profile():
    pass

def save_difficulty_level():
    pass

def get_video_by_youtube_video_id(youtube_video_id:str,db:Session):
    stmt = select(Video).where(
    Video.youtube_video_id == youtube_video_id
)

    row = db.execute(stmt).scalars().first()
    return row