from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class VocabularyReviewLog(Base):
    __tablename__ = "vocabulary_review_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_saved_vocab_id: Mapped[int] = mapped_column(
        ForeignKey("user_saved_vocabulary.id", ondelete="CASCADE"), nullable=False
    )

    grade: Mapped[int] = mapped_column(Integer, nullable=False)

    review_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    scheduled_interval_days: Mapped[int] = mapped_column(Integer, nullable=False)

    elapsed_interval_days: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    user_saved_vocab = relationship("UserSavedVocabulary", backref="review_logs")