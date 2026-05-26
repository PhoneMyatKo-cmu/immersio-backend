from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.endpoints import TempVideo, ai_explanation, caption, user_add_video, vocab
from api.v1.endpoints.users import router as user_router
from db.base import Base, engine
from models.ai_explanation_cache import AI_Explanation_Cache
from models.processed_caption import ProcessedCaption
from models.sentence import Sentence
from models.user import User
from models.user_vocab_library import UserVocabLibrary
from models.user_vocab_profile import UserVocabProfile
from models.video import Video
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


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"message": "Immersio backend API running"}


app.include_router(user_add_video.router)
app.include_router(vocab.router)
app.include_router(caption.router)
app.include_router(TempVideo.router)
app.include_router(ai_explanation.router)
