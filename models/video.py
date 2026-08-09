import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class VideoSource(str, enum.Enum):
    curated = "curated"
    user_submitted = "user_submitted"


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    youtube_video_id: Mapped[str] = mapped_column(String(500), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)

    thumbnail_url: Mapped[str] = mapped_column(String(500), nullable=False)

    channel_name: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)

    is_shadowing_ready: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    source: Mapped[VideoSource] = mapped_column(
        Enum(VideoSource, name="video_source_enum"),
        nullable=False,
        default=VideoSource.user_submitted,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    added_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    added_by_user = relationship("User", back_populates="added_videos")

    captions = relationship(
        "Caption", back_populates="video", cascade="all, delete-orphan"
    )

    shadowingsentences = relationship(
        "ShadowingSentence", back_populates="video", cascade="all, delete-orphan"
    )
