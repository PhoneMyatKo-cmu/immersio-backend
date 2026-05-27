from sqlalchemy import func, text
from models.video import DifficultyLevel, Video
from sqlalchemy.orm import Session
from sqlalchemy import select
import isodate

def check_video_exists(youtube_video_id:str,
                             db:Session)->Video | None:
    
    """ Check whether video exists in the database
        Return video if exists, none if doesn't exist
    """
    
    result=db.scalars(
        select(Video).where(Video.youtube_video_id==youtube_video_id)).first()
    return result 


def save_video(meta_data:dict , suitability : dict, db:Session ):
    """ save video metadata to the database"""
    
    # duration_funtion to be implemented later
    try:
        video=Video(
            youtube_video_id=meta_data["video_id"],
            title=meta_data["title"],
            thumbnail_url=meta_data["thumbnail_url"],
            channel_name=meta_data["channel_name"],
            duration_seconds=isodate.parse_duration(meta_data["duration"]).total_seconds(),
        )
        db.add(video)
        db.commit()
    except Exception as e:
        print(e)
        raise e
    
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

def get_videos_by_difficulty_level(difficulty_level: DifficultyLevel,db:Session, search: str, page: int, page_size: int):
    stmt = select(Video).where(
    Video.difficulty_level == difficulty_level
    ).order_by(
        Video.created_at.desc()
    )

    if search:
        stmt = stmt.where(Video.title.ilike(f"%{search}%"))

    rows = db.execute(stmt.limit(page_size).offset((page - 1) * page_size)).scalars().all()
    
    total_videos = get_total_video_count(db, stmt)
    return rows, total_videos

def get_videos(db:Session, search: str = None, page: int = 1, page_size: int = 6):
    stmt = select(Video).order_by(
        Video.created_at.desc()
    )
    
    if search:
        stmt = stmt.where(Video.title.ilike(f"%{search}%"))

    rows = db.execute(stmt.limit(page_size).offset((page - 1) * page_size)).scalars().all()
    total_videos = get_total_video_count(db, stmt)
    return rows, total_videos

def get_total_video_count(db:Session, stmt:select):
    total_videos = db.scalar(select(func.count()).select_from(stmt.subquery()))
    return total_videos