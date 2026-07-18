import enum

from sqlalchemy import INTEGER, Enum, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class EstimatedLevel(str, enum.Enum):
    N1 = "N1"
    N2 = "N2"
    N3 = "N3"
    N4 = "N4"
    N5 = "N5"
    UNKNOWN = "UNKNOWN"


class Vocabulary(Base):
    __tablename__ = "vocabulary"

    id: Mapped[int] = mapped_column(INTEGER, primary_key=True, autoincrement=True)

    japanese_form: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    reading: Mapped[str] = mapped_column(String(255), nullable=False)

    meanings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)

    lemma: Mapped[str] = mapped_column(String(255), nullable=False)

    estimated_level: Mapped[EstimatedLevel] = mapped_column(
        Enum(EstimatedLevel, name="vocab_level_enum"),
        nullable=False,
        default=EstimatedLevel.UNKNOWN,
    )
