from sqlalchemy.orm import Session
from db.base import get_db
from models.processed_caption import ProcessedCaption

def save_tokenized_captions(tokenized_captions:list[dict],video_id:int,db:Session):
    try:
        for caption in tokenized_captions:
            tokenized_caption=ProcessedCaption(
                video_id=video_id,
                caption_index=caption["index"],
                tokens=caption["tokens"],
                start_time=caption["start"],
                end_time=float(caption["start"])+float(caption["duration"]),
                duration=caption["duration"]
            )
            
            db.add(tokenized_caption)
        db.commit()
    except Exception as e:
        db.rollback()
        print(e)
        raise e
    
    return len(tokenized_captions)
    