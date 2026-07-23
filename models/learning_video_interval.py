from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

class LearningVideoInterval(Base):
    __tablename__ = "learning_video_interval"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("learning_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    start_time: Mapped[float] = mapped_column(nullable=False)
    end_time: Mapped[float] = mapped_column(nullable=False)

    # Relationships
    session = relationship("LearningSession", backref="video_intervals")
