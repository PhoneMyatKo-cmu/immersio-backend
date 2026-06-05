from sqlalchemy import select, text
from sqlalchemy.orm import Session

from models.vocab import EstimatedLevel, Vocabulary
from utils.dictionary_lookup_helpers import lookup_word_full


def save_vocabularies(tokens: list, db: Session):
    unique_tokens = []
    seen = set()
    for token in tokens:
        key = token[0]
        if key in seen:
            continue
        seen.add(key)
        unique_tokens.append(token)

    for token in unique_tokens:
        if check_duplicate(token[0], db):
            print(f"Duplicate:{token[0]}")
            continue
        looked_up_token = lookup_word_full(token)
        if looked_up_token["found"]:
            vocab = Vocabulary(
                japanese_form=token[0],
                reading=looked_up_token["romanji_reading"],
                meanings=looked_up_token["meanings"],
                estimated_level=EstimatedLevel(looked_up_token["jlpt_tier"]),
            )
            db.add(vocab)
    db.commit()
    return tokens


def check_duplicate(japanese_form: str, db: Session):
    # result=db.execute(
    #                     text("SELECT id FROM vocabulary WHERE japanese_form = :jf"),
    #                     {"jf":japanese_form}
    #                 )

    result = db.scalars(
        select(Vocabulary).where(Vocabulary.japanese_form == japanese_form)
    ).first()

    return result is not None


def get_vocab_by_surface_form(surface_form: str, db: Session) -> Vocabulary | None:

    result = db.scalars(
        select(Vocabulary).where(Vocabulary.japanese_form == surface_form)
    ).first()

    return result
