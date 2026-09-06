import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class EstimatedLevel(str, enum.Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    LEARNER = "LEARNER"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)

    last_name: Mapped[str] = mapped_column(String(100), nullable=False)

    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    estimated_level: Mapped[EstimatedLevel] = mapped_column(
        Enum(EstimatedLevel, name="estimated_level_enum"),
        nullable=False,
        default=EstimatedLevel.beginner,
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"), nullable=False, default=UserRole.LEARNER
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )

    added_videos = relationship("Video", back_populates="added_by_user")

    # total_videos_viewed: Mapped[int] = mapped_column(
    #     default=0,
    #     doc="Total number of videos viewed by the user"
    # )

    # total_study_time: Mapped[int] = mapped_column(
    #     default=0,
    #     doc="Total study time in seconds"
    # )

    # total_vocab_seen: Mapped[int] = mapped_column(
    #     default=0,
    #     doc="Total number of unique vocabulary items seen by the user"
    # )

    # total_known_vocab: Mapped[int] = mapped_column(
    #     default=0,
    #     doc="Total number of vocabulary items which have been seen over a certain threshold and are considered 'known' by the user"
    # )

    # total_vocab_mastered: Mapped[int] = mapped_column(
    #     default=0,
    #     doc="Total number of vocabulary items which have ease factors above a certain threshold through spaced repetition and are considered 'mastered' by the user"
    # )

    # streak: Mapped[int] = mapped_column(
    #     default=0,
    #     doc="Current streak of consecutive days the user has studied"
    # )

    # longest_streak: Mapped[int] = mapped_column(
    #     default=0,
    #     doc="Longest streak of consecutive days the user has studied"
    # )
