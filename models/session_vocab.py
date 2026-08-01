from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base
from sqlalchemy import ForeignKey, UniqueConstraint

class SessionVocabulary(Base):
    __tablename__ = "session_vocabulary"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), nullable=False
    )
    vocab_id: Mapped[int] = mapped_column(
        ForeignKey("vocabulary.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (UniqueConstraint("session_id", "vocab_id", name="session_vocab_unique"),)

    # Relationships
    session = relationship("LearningSession", backref="session_vocabularies")