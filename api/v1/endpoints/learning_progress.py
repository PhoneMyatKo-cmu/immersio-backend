

from datetime import date, timedelta

from fastapi import APIRouter
from fastapi.params import Depends
from sqlalchemy.orm import Session

from db.base import get_db
from services.daily_progress.daily_progress_service import get_all_time_progress, get_daily_progress_by_date_range
from services.user_vocab_exposure.user_vocab_exposure_service import get_vocab_known_by_user
from tests.utils.daily_progress_helper import calculate_total_videos_watched, summarize_daily_progresses
from tests.utils.daily_progress_helper import calculate_total_videos_watched


router = APIRouter(prefix="/learning-progress")

@router.get("/{user_id}")
async def get_learning_progress(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Fetches the all-time learning progress for the given user.
    """

    daily_progresses = get_all_time_progress(user_id, db)
    summary = summarize_daily_progresses(daily_progresses, ["study_seconds", "total_videos_watched", "vocab_seen", "vocab_known", "streak"], db)

    return {
                "study_seconds": summary["study_seconds"],
                "total_videos_watched": summary["total_videos_watched"],
                "total_vocab_seen": summary["vocab_seen"],
                "total_vocab_known": summary["vocab_known"],
                "streak": summary["streak"]
            }

@router.get("/chart/{user_id}/{type}")
async def get_learning_progress_chart(
    user_id: int,
    type: str,
    period_days: int | str = 7,
    db: Session = Depends(get_db)
):
    """
    Fetches the learning progress chart data for the given user and type.
    """
    today = date.today()
    print(period_days)
    if isinstance(period_days, str):
        try:
            period_days = int(period_days)
        except ValueError:
            if period_days.lower() == "all_time":
                period_days = (today - date(1970, 1, 1)).days + 1
            elif period_days.lower() == "month":
                period_days = 30
            elif period_days.lower() == "week":
                period_days = 7
    start_date = today - timedelta(days=period_days - 1)
    print(f"Start date for chart data: {start_date}, End date: {today}")
    daily_progresses = get_daily_progress_by_date_range(user_id, start_date, today, db)
    previous_progresses = get_daily_progress_by_date_range(user_id, None, start_date - timedelta(days=1), db)
    previous_summary = summarize_daily_progresses(previous_progresses, [type], db)

    if type == "study_seconds":
        chart_data = [{"day": progress.day, "value": progress.study_seconds} for progress in daily_progresses]
    elif type == "videos_watched":
        chart_data = [{"day": progress.day, "value": progress.videos_watched} for progress in daily_progresses]
    elif type == "total_videos_watched":
        chart_data = [{"day": progress.day, "value": progress.total_videos_watched} for progress in daily_progresses]
    elif type == "vocab_seen":
        chart_data = [{"day": progress.day, "value": progress.new_vocab_seen} for progress in daily_progresses]
    elif type == "vocab_known":
        chart_data = [{"day": progress.day, "value": progress.new_vocab_known} for progress in daily_progresses]
    elif type == "streak":
        chart_data = [{"day": progress.day, "value": progress.streak} for progress in daily_progresses]
    else:
        return {"error": "Invalid type specified."}

    return {
        "chart_data": chart_data,
        "previous_summary": previous_summary
    }

@router.get("/test/{user_id}")
async def test_learning_progress(user_id: int, db: Session = Depends(get_db)):
    known_vocab = get_vocab_known_by_user(user_id, db)
    return {"known_vocab": known_vocab}