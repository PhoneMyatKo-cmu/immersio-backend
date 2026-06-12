import enum

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class ConfidenceLevel(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class ContextualExplanation(Base):
    __tablename__ = "contextual_explanations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    vocab_id: Mapped[int] = mapped_column(
        ForeignKey("vocabulary.id", ondelete="CASCADE"), nullable=False, index=True
    )

    caption_id: Mapped[int] = mapped_column(
        ForeignKey("captions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    explanation: Mapped[str] = mapped_column(String(3000), nullable=False)

    examples: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)

    confidence_level: Mapped[ConfidenceLevel] = mapped_column(
        Enum(ConfidenceLevel, name="confidence_level_enum"),
        nullable=False,
    )

    dictionary_mismatch_detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
