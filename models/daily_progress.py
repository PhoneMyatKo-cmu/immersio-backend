from datetime import date

from db.base import Base
from sqlalchemy import Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

class DailyProgress(Base):
    __tablename__ = "learning_progress"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, unique=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    study_seconds: Mapped[int] = mapped_column(nullable=False, default=0)
    videos_watched: Mapped[int] = mapped_column(nullable=False, default=0)
    total_videos_watched: Mapped[int] = mapped_column(nullable=False, default=0)
    new_vocab_seen: Mapped[int] = mapped_column(nullable=False, default=0)
    new_vocab_known: Mapped[int] = mapped_column(nullable=False, default=0)
    sessions_count: Mapped[int] = mapped_column(nullable=False, default=0)
    streak: Mapped[int] = mapped_column(nullable=False, default=0)

    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_user_day"),)

    # Relationships
    user = relationship("User", backref="daily_progress")
