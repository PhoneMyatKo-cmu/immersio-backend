import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class SRSState(str, enum.Enum):
    new = "not_studied"
    studying = "studying"
    mastered = "mastered"


class UserVocabLibrary(Base):
    __tablename__ = "user_vocab_library"

    __table_args__ = (UniqueConstraint("user_id", "vocab_id", name="uq_user_vocab"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    vocab_id: Mapped[str] = mapped_column(
        ForeignKey("vocabulary.id", ondelete="CASCADE"), nullable=False, index=True
    )

    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="SET NULL"), nullable=False, index=True
    )

    caption_id: Mapped[int] = mapped_column(
        ForeignKey("processed_captions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    timestamp: Mapped[float] = mapped_column(Float, nullable=True)

    srs_state: Mapped[SRSState] = mapped_column(
        Enum(SRSState, name="srs_state_enum"), nullable=False, default=SRSState.new
    )

    ease_factor: Mapped[float] = mapped_column(Float, nullable=False, default=2.5)

    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    next_review_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    last_review_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    first_saved_date: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Optional relationships (useful for ORM navigation)
    user = relationship("User", backref="vocab_libraries")
    vocab = relationship("Vocabulary", backref="user_entries")
    video = relationship("Video", backref="vocab_libraries")
    caption = relationship("ProcessedCaption", backref="vocab_libraries")
