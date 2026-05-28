from pydantic import BaseModel, ConfigDict


class VideoRespone(BaseModel):
    youtube_video_id: str
    title: str
    thumbnail_url: str
    channel_name: str
    duration_seconds: int

    model_config = ConfigDict(from_attributes=True)
