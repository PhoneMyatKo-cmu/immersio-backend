from datetime import datetime

from pydantic import BaseModel, ConfigDict

from models.video import VideoSource


class VideoResponse(BaseModel):
    youtube_video_id: str
    title: str
    thumbnail_url: str
    channel_name: str
    duration_seconds: int

    model_config = ConfigDict(from_attributes=True)


class VideoUrl(BaseModel):
    youtube_url: str


class VideoAdminRead(BaseModel):
    id: int
    youtube_video_id: str
    title: str
    thumbnail_url: str
    channel_name: str
    duration_seconds: int
    is_shadowing_ready: bool
    source: VideoSource
    is_active: bool
    added_by: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VideoAdminListResponse(BaseModel):
    items: list[VideoAdminRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class SourceBreakdown(BaseModel):
    curated: int
    user_submitted: int


class TopContributor(BaseModel):
    added_by: int
    name: str | None
    count: int


class VideoStatsResponse(BaseModel):
    total: int
    active: int
    inactive: int
    by_source: SourceBreakdown
    shadowing_ready: int
    shadowing_not_ready: int
    added_last_7_days: int
    added_last_30_days: int
    # top_contributors: list[TopContributor]
