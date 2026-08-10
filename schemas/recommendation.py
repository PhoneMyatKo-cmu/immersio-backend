from pydantic import BaseModel

from models.video import Video


class RecommendedVideo(BaseModel):
    video: Video
    score: int
