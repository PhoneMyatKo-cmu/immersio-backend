from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Enum, JSON
from sqlalchemy.orm import Mapped, mapped_column,relationship
import enum

from db.base import Base


class DifficultyLevel(str, enum.Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    url: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    thumbnail_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )


    channel_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    difficulty_level: Mapped[DifficultyLevel] = mapped_column(
        Enum(DifficultyLevel, name="difficulty_level_enum"),
        nullable=False,
        default=DifficultyLevel.beginner
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    duration_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    
    processed_captions = relationship(
    "ProcessedCaption",
    back_populates="video",
    cascade="all, delete-orphan"
    ) 
    
    sentences=relationship(
        "Sentence",
        back_populates="video",
        cascade="all, delete-orphan"
        )