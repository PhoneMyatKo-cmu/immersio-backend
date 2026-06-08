import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.endpoints import (
    ai_explanation,
    caption,
    home_feed,
    sentence,
    shadowing,
    user_add_video,
    video_detail,
    vocab,
)
from api.v1.endpoints.users import router as user_router
from db.base import Base, engine
from models.ai_explanation_cache import AI_Explanation_Cache
from models.processed_caption import ProcessedCaption
from models.sentence import Sentence
from models.user import User
from models.user_vocab_library import UserVocabLibrary
from models.user_vocab_profile import UserVocabProfile
from models.video import Video
from models.video_vocab_profile import VideoVocabProfile
from models.vocab import Vocabulary

app = FastAPI()

app.include_router(user_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # CRA dev server
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"message": "Immersio backend API running"}


app.include_router(user_add_video.router)
app.include_router(vocab.router)
app.include_router(caption.router)
app.include_router(video_detail.router)
app.include_router(ai_explanation.router)

app.include_router(home_feed.router)
app.include_router(shadowing.router)
app.include_router(sentence.router)
