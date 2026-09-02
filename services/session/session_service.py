from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.learning_session import LearningSession
from models.learning_video_interval import LearningVideoInterval
from schemas.session import SessionData


def save_learning_session(session_data: SessionData, db: Session):
    if not session_data.intervals:
        raise ValueError("Intervals list cannot be empty.")

    existing_session = get_learning_sessions(session_data.id, db)
    if existing_session:
        if (
            existing_session.user_id != session_data.user_id
            or existing_session.video_id != session_data.video_id
            or existing_session.start_time
            != (datetime.fromtimestamp(session_data.start_time))
        ):
            raise ValueError(
                f"Session with id {session_data.id} already exists with different data."
            )
        if existing_session.end_time < (datetime.fromtimestamp(session_data.end_time)):
            existing_session.end_time = datetime.fromtimestamp(session_data.end_time)
    else:
        learning_session = LearningSession(
            id=session_data.id,
            user_id=session_data.user_id,
            video_id=session_data.video_id,
            start_time=datetime.fromtimestamp(session_data.start_time),
            end_time=datetime.fromtimestamp(session_data.end_time),
        )
        db.add(learning_session)
        existing_session = (
            learning_session  # Set existing_session to the newly created session
        )

    for interval in session_data.intervals:
        learning_video_interval = LearningVideoInterval(
            session_id=existing_session.id,
            start_time=interval.start_time,
            end_time=interval.end_time,
        )
        db.add(learning_video_interval)

    db.commit()

    return existing_session


def get_learning_sessions(id: str, db: Session):
    return db.query(LearningSession).filter(LearningSession.id == id).first()


def get_learning_sessions_by_user_and_video(user_id: int, video_id: int, db: Session):
    return (
        db.query(LearningSession)
        .filter(
            LearningSession.user_id == user_id, LearningSession.video_id == video_id
        )
        .all()
    )


def get_learning_sessions_by_user(user_id: int, db: Session):
    return db.query(LearningSession).filter(LearningSession.user_id == user_id).all()


def get_learning_sessions_by_user_and_day(user_id: int, day: date, db: Session):
    return (
        db.query(LearningSession)
        .filter(
            LearningSession.user_id == user_id,
            LearningSession.end_time >= day,
            LearningSession.end_time < day + timedelta(days=1),
        )
        .all()
    )


def last_watched_map(user_id: int, db: Session) -> dict[int, datetime]:
    """Most recent watch time per video for one user (§6).

    Built once per request; the orchestrator passes last_watched_map.get(video_id)
    into each score_video call. Videos never watched are simply absent (→ no
    recency penalty, since recency_penalty(None, ...) returns 0.0).
    """
    rows = db.execute(
        select(
            LearningSession.video_id,
            func.max(LearningSession.end_time),
        )
        .where(LearningSession.user_id == user_id)
        .group_by(LearningSession.video_id)
    ).all()

    return {video_id: last_end for video_id, last_end in rows}
