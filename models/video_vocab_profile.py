from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class VideoVocabulary(Base):
    __tablename__ = "video_vocabulary"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    vocab_id: Mapped[int] = mapped_column(
        ForeignKey("vocabulary.id", ondelete="CASCADE"), nullable=False
    )
    frequency: Mapped[int] = mapped_column(default=1)

    __table_args__ = (UniqueConstraint("video_id", "vocab_id", name="uq_video_vocab"),)
