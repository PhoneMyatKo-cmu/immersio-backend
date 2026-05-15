from sqlalchemy.orm import Session
from models.sentence import Sentence

def save_context_sentence(sentences:list,video_db_id:int,db:Session):
    for st in sentences:
        sentence=Sentence(
            video_id=video_db_id,
            sentence_index=st["sentence_index"],
            text=st["text"],
            start_time=st["start"],
            end_time=st["end"],
            duration=st["duration"]
            )
        db.add(sentence)
    number_of_sentences=len(sentences)
    db.commit()
    return {"number_of_sentences":number_of_sentences}


    