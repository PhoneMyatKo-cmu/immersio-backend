from pydantic import BaseModel, ConfigDict

from schemas.video import VideoResponse


class RecommendationReasons(BaseModel):
    """Per-term breakdown of a video's score, for an explainable feed / debugging.

    Populated only in debug mode; omitted (None) in normal responses.
    """

    coverage: float          # frequency-weighted comprehension coverage C (§3)
    comprehension_fit: float # band score derived from C
    learning_value: float    # "+1" new-word value (§4)
    srs_bonus: float         # due/struggling deck words present (§5)
    recency_penalty: float   # decay penalty for a recent watch (§6)

    model_config = ConfigDict(from_attributes=True)


class RecommendedVideo(BaseModel):
    id: int
    video: VideoResponse
    score: float
    reasons: RecommendationReasons | None = None

    model_config = ConfigDict(from_attributes=True)


class RecommendationResponse(BaseModel):
    items: list[RecommendedVideo]
    page: int
    page_size: int
    total_pages: int
