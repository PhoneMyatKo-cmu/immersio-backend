from models.vocab import Vocabulary
from utils.dictionary_lookup_helpers import lookup_word_full
from sqlalchemy.orm import Session
from sqlalchemy import select,text

def save_vocabularies(tokens:list,db:Session):
    unique_tokens=list(set(tokens))
    for token in unique_tokens:
        if check_duplicate(token,db):
            print(f"Duplicate:{token}")
            continue
        looked_up_token=lookup_word_full(token)
        if looked_up_token["found"]:
            vocab=Vocabulary(
                japanese_form=token,
                reading=looked_up_token["romanji_reading"],
                senses=looked_up_token["meanings"]   
            )
            db.add(vocab)
    db.commit()
    return tokens


def check_duplicate(japanese_form:str,db:Session):
    result=db.execute(
                        text("SELECT id FROM vocabulary WHERE japanese_form = :jf"),
                        {"jf":japanese_form}
                    )
    
    return result.fetchone() is not None
        