from sqlalchemy import String, Enum, ARRAY,INTEGER
from sqlalchemy.dialects.postgresql import JSONB
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

    id: Mapped[int] = mapped_column(
        INTEGER,
        primary_key=True,
        autoincrement=True
    )

    japanese_form: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )

    reading: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    meanings: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=list
    )
    

    estimated_level: Mapped[EstimatedLevel] = mapped_column(
        Enum(EstimatedLevel, name="vocab_level_enum"),
        nullable=False,
        default=EstimatedLevel.unknown
    )
    
    