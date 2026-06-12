from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


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

    captions = relationship(
        "Caption", back_populates="video", cascade="all, delete-orphan"
    )

    shadowingsentences = relationship(
        "ShadowingSentence", back_populates="video", cascade="all, delete-orphan"
    )
