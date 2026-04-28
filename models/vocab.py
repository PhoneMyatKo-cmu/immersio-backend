from sqlalchemy import String, Enum, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
import enum

from  db.base import Base


class EstimatedLevel(str, enum.Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"
    unknown = "unknown"


class Vocabulary(Base):
    __tablename__ = "vocabulary"

    id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True
    )

    japanese_form: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )

    # list of meanings (JSON array)
    meaning: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False
    )

    reading: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    part_of_speech: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    estimated_level: Mapped[EstimatedLevel] = mapped_column(
        Enum(EstimatedLevel, name="vocab_level_enum"),
        nullable=False,
        default=EstimatedLevel.unknown
    )