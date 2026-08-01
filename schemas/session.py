from pydantic import BaseModel

class Interval(BaseModel):
    start_time: float
    end_time: float

class SessionData(BaseModel):
    id: str
    user_id: int
    video_id: int
    start_time: float
    end_time: float
    intervals: list[Interval]
