from fastapi import FastAPI
from db.base import Base,engine
from models.user import User
from models.video import Video
from models.vocab import Vocabulary
from models.sentence import Sentence
from models.processed_caption import ProcessedCaption
from models.user_vocab_library import UserVocabLibrary
from models.user_vocab_profile import UserVocabProfile
from api.v1.endpoints.users import router as user_router

app = FastAPI()

app.include_router(user_router)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"message": "Immersio backend API running"}