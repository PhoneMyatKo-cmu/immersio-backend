

from datetime import date, datetime

from sqlalchemy.orm import Session

from models.daily_progress import DailyProgress
from models.learning_session import LearningSession
from services.session.session_service import get_learning_sessions_by_user_and_day
from tests.utils.daily_progress_helper import calculate_streak, create_daily_progress, update_daily_progress

def save_daily_progress(session: LearningSession, db: Session):
    """
    Creates or updates the DailyProgress entry for the given learning session.
    """
    user_id = session.user_id
    day = session.end_time.date()
    daily_progress = get_daily_progress(user_id, day, db)
    if not daily_progress:
        daily_progress = create_daily_progress(user_id, day)
        db.add(daily_progress)
    sessions = get_learning_sessions_by_user_and_day(user_id, day, db)
    daily_progress = update_daily_progress(sessions, daily_progress, db)
    daily_progress.streak = calculate_streak(session, db)
    db.commit()

def get_all_time_progress(user_id: int, db: Session):
    """
    Fetches the all-time progress for the given user.
    """
    return db.query(DailyProgress).filter(
        DailyProgress.user_id == user_id
    ).all()

def get_daily_progress(user_id: int, day: date, db: Session):
    """
    Fetches the DailyProgress entry for the given user and day.
    """
    return db.query(DailyProgress).filter(
        DailyProgress.user_id == user_id,
        DailyProgress.day == day
    ).first()

def get_daily_progress_by_date_range(user_id: int, start_date: date, end_date: date, db: Session):
    """
    Fetches the DailyProgress entries for the given user within the specified date range.
    """
    if start_date is None and end_date is None:
        return db.query(DailyProgress).filter(
            DailyProgress.user_id == user_id
        ).all()
    if start_date is None:
        return db.query(DailyProgress).filter(
            DailyProgress.user_id == user_id,
            DailyProgress.day <= end_date
        ).all()
    if end_date is None:
        return db.query(DailyProgress).filter(
            DailyProgress.user_id == user_id,
            DailyProgress.day >= start_date
        ).all()
    return db.query(DailyProgress).filter(
        DailyProgress.user_id == user_id,
        DailyProgress.day >= start_date,
        DailyProgress.day <= end_date
    ).all()
