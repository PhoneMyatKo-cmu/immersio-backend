from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class ProcessedCaption(Base):
    __tablename__ = "processed_captions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )

    caption_index: Mapped[int] = mapped_column(Integer, nullable=False)

    text: Mapped[str] = mapped_column(String(1000), nullable=False)

    # tokenized words for NLP / shadowing
    tokens: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    start_time: Mapped[float] = mapped_column(Float, nullable=False)

    end_time: Mapped[float] = mapped_column(Float, nullable=False)

    duration: Mapped[float] = mapped_column(Float, nullable=False)

    translation: Mapped[str] = mapped_column(String(1000), nullable=True)

    video = relationship("Video", back_populates="processed_captions")
