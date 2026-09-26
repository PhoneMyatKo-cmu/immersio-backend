import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.endpoints import (
    ai_explanation,
    caption,
    learning_progress,
    sentence,
    session,
    shadowing,
    spaced_repetition_review,
    user_admin,
    user_vocab_exposure,
    video,
    video_admin,
    video_submission,
    vocab,
)
from api.v1.endpoints.auth import router as user_router
from db.base import Base, engine
from models.ai_explanation_cache import ContextualExplanation
from models.processed_caption import Caption
from models.sentence import ShadowingSentence
from models.user import User
from models.user_vocab_library import UserSavedVocabulary
from models.user_vocab_profile import UserVocabularyExposure
from models.video import Video
from models.video_vocab_profile import VideoVocabulary
from models.vocab import Vocabulary
from utils.shadowing_helpers import warm_up_scoring

app = FastAPI()

app.include_router(user_router)
app.add_middleware(
    CORSMiddleware,
    # Comma-separated in CORS_ORIGINS (e.g. the deployed frontend URL);
    # falls back to the local dev servers.
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
        ).split(",")
        if origin.strip()
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
    # Load Whisper and compile pyin up front so the first pronunciation
    # score after a (re)start isn't slow. Off by default (tests, local dev).
    if os.getenv("WHISPER_PRELOAD") == "1":
        warm_up_scoring()


@app.get("/")
def root():
    return {"message": "Immersio backend API running"}


app.include_router(video_submission.router)
app.include_router(vocab.router)
app.include_router(caption.router)
app.include_router(ai_explanation.router)

app.include_router(video.router)
app.include_router(shadowing.router)
app.include_router(sentence.router)
app.include_router(session.router)
app.include_router(learning_progress.router)
app.include_router(user_vocab_exposure.router)
app.include_router(spaced_repetition_review.router)
app.include_router(video_admin.router)
app.include_router(user_admin.router)
