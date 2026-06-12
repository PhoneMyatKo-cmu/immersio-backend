from datetime import datetime
from sqlalchemy import Integer, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from db.base import Base


class VocabStatus(str, enum.Enum):
    seen = "SEEN"
    know = "KNOW"


class UserVocabularyExposure(Base):
    __tablename__ = "user_vocabulary_exposure"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    vocab_id: Mapped[str] = mapped_column(
        ForeignKey("vocabulary.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    seen_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    status: Mapped[VocabStatus] = mapped_column(
        Enum(VocabStatus, name="vocab_status_enum"),
        nullable=False,
        default=VocabStatus.seen
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True
    )

    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True
    )

    # optional ORM relationships
    user = relationship("User", backref="vocabulary_exposures")
    vocab = relationship("Vocabulary", backref="user_exposures")