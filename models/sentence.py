from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class ShadowingSentence(Base):
    __tablename__ = "shadowingsentences"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )

    sentence_index: Mapped[int] = mapped_column(Integer, nullable=False)

    text: Mapped[str] = mapped_column(String(1000), nullable=False)

    start_time: Mapped[float] = mapped_column(Float, nullable=False)

    end_time: Mapped[float] = mapped_column(Float, nullable=False)

    duration: Mapped[float] = mapped_column(Float, nullable=False)

    translation: Mapped[str] = mapped_column(String(1000), nullable=True)

    # Relationship (optional but recommended)
    video = relationship("Video", back_populates="shadowingsentences")
