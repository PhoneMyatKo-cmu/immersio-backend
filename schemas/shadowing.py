from pydantic import BaseModel
from fastapi import UploadFile

class ShadowingRequest(BaseModel):
    file: UploadFile
    caption: str
    start_time: float = 0.0
    end_time: float = None
    video_id: str = None

class ShadowingResponse(BaseModel):
    cer: float
    user_katakana: str
    caption_katakana: str
    pitch_score: float
    pitch_comparison_figure: str  # Base64-encoded image
    user_pitch: list[float]
    reference_pitch: list[float]

class PronunciationExplanationRequest(BaseModel):
    cer: float
    pitch_score: float
    user_katakana: str
    caption_katakana: str
    user_pitch: list[float]
    reference_pitch: list[float]
    caption: str

class PronunciationExplanationResponse(BaseModel):
    summary: str
    pronunciation_feedback: list[str]
    pitch_feedback: list[str]
    strengths: list[str]
    improvements: list[str]
