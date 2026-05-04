from sqlalchemy import text
from models.video import Video
from sqlalchemy.orm import Session
from sqlalchemy import select

async def check_video_exists(youtube_video_id:str,
                             db:Session)->bool:
    
    """ Check whether video exists in the database"""
    result=db.execute(
                        text("SELECT id FROM videos WHERE url = :vid"),
                        {"vid":youtube_video_id}
                    )
    
    return result.fetchone() is not None


async def save_video(meta_data:dict , suitability : dict, db:Session ):
    """ save video metadata to the database"""
    
    # duration_funtion to be implemented later
    video=Video(
        url=meta_data["video_id"],
        title=meta_data["title"],
        thumbnail_url=meta_data["thumbnail_url"],
        channel_name=meta_data["channel_name"],
        duration_seconds=100,
    )
    db.add(video)
    # await db.execute(text("""
    #                  INSERT INTO videos
    #                  (
    #                      url,
    #                      title,
    #                      thumbnail_url,
    #                      channel_name
    #                  )
    #                  VALUES(
                         
    #                      :youtube_video_url,
    #                      :title,
    #                      :thumbnail_url,
    #                      :channel_name
    #                  )
    #                  """),
    #                  {
    #                      "youtube_video_url":meta_data["video_id"],
    #                      "title":meta_data["title"],
    #                      "thumbnail_url":meta_data["thumbnail_url"],
    #                      "channel_name":meta_data["channel_name"]
    #                  })
    
    db.commit()
    
    return{
        "title":meta_data["title"]
    }
    

async def save_vocabulary_profile():
    pass

async def save_difficulty_level():
    pass

def get_video_by_url(url:str,db:Session):
    stmt = select(Video).where(
    Video.url == url
)

    row = db.execute(stmt).scalars().first()
    return row