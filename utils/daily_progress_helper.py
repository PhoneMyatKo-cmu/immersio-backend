
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models.daily_progress import DailyProgress
from models.learning_session import LearningSession
from services.session.session_service import get_learning_sessions_by_user, get_learning_sessions_by_user_and_day
from services.user_vocab_exposure.user_vocab_exposure_service import get_user_vocab_exposure, get_vocab_known_by_user, get_vocab_seen_by_user


def create_daily_progress(user_id: int, day: date):
    """
    Creates a new DailyProgress entry for the given user and day.
    """
    daily_progress = DailyProgress(
        user_id=user_id,
        day=day,
        study_seconds=0,
        videos_watched=0,
        total_videos_watched=0,
        new_vocab_seen=0,
        new_vocab_known=0,
        sessions_count=0,
        streak=0
    )
    return daily_progress

def update_daily_progress(sessions: list[LearningSession], daily_progress: DailyProgress, db: Session):
    """
    Updates the DailyProgress entry based on the provided LearningSession.
    """
    daily_progress.study_seconds = calculate_study_seconds(sessions)
    daily_progress.videos_watched = calculate_daily_videos_watched(sessions)
    daily_progress.total_videos_watched = calculate_total_videos_watched(sessions[0].user_id, db)
    daily_progress.new_vocab_seen = calculate_new_vocab_seen(sessions, db)
    daily_progress.new_vocab_known = calculate_new_vocab_known(sessions, db)
    daily_progress.sessions_count = len(sessions)

    return daily_progress

def calculate_study_seconds(sessions: list[LearningSession]):
    """
    Calculates the total study seconds from the provided LearningSession.
    """
    total_seconds = sum((session.end_time - session.start_time).total_seconds() for session in sessions)
    return int(total_seconds)

def calculate_daily_videos_watched(sessions: list[LearningSession]):
    """
    Calculates the total number of unique videos watched from the provided LearningSession.
    """
    unique_videos = {session.video_id for session in sessions}
    return len(unique_videos)

def calculate_total_videos_watched(user_id: int, db: Session):
    """
    Calculates the total number of unique videos watched by the user across all sessions.
    """
    sessions = get_learning_sessions_by_user(user_id, db)
    unique_videos = {session.video_id for session in sessions}
    return len(unique_videos)

def calculate_new_vocab_seen(sessions: list[LearningSession], db: Session):
    """
    Calculates the total number of vocabulary words seen from the provided LearningSession.
    """
    vocab_seen_all_time = get_vocab_seen_by_user(sessions[0].user_id, db)
    vocab_seen_count_all_time = {vocab.vocab_id: vocab.seen_count for vocab in vocab_seen_all_time}
    vocab_seen_count_today = {}
    for session in sessions:
        for vocab in session.session_vocabularies:
            if vocab.vocab_id not in vocab_seen_count_today:
                vocab_seen_count_today[vocab.vocab_id] = 1
            else:
                vocab_seen_count_today[vocab.vocab_id] += 1
    old_vocab_seen_count = {vocab_id: (vocab_seen_count_all_time.get(vocab_id, 0) - count) for vocab_id, count in vocab_seen_count_today.items()}
    new_vocabs = [vocab_id for vocab_id, count in old_vocab_seen_count.items() if count == 0]
    
    return len(new_vocabs)

def calculate_new_vocab_known(sessions: list[LearningSession], db: Session):
    """
    Calculates the total number of vocabulary words known from the provided LearningSession.
    """
    total_vocab_known_all_time = get_vocab_known_by_user(sessions[0].user_id, db)
    total_vocab_seen_count_all_time = {vocab.vocab_id: vocab.known_count for vocab in total_vocab_known_all_time}
    vocab_seen_count_today = {}
    for session in sessions:
        for vocab in session.session_vocabularies:
            if vocab.vocab_id not in vocab_seen_count_today:
                vocab_seen_count_today[vocab.vocab_id] = 1
            else:
                vocab_seen_count_today[vocab.vocab_id] += 1
    old_vocab_seen_count = {vocab_id: (total_vocab_seen_count_all_time.get(vocab_id, 0) - count) for vocab_id, count in vocab_seen_count_today.items()}
    new_vocabs = [vocab_id for vocab_id, count in old_vocab_seen_count.items() if count <= 10 and count >= 0]

    return len(new_vocabs)

def calculate_streak(session: LearningSession, db: Session):
    """
    Calculates the current streak based on the provided LearningSession.
    """
    from services.daily_progress.daily_progress_service import get_daily_progress
    user_id = session.user_id
    day = session.end_time.date()
    previous_day = day - timedelta(days=1)
    
    previous_day_progress = get_daily_progress(user_id, previous_day, db)
    
    if previous_day_progress:
        return previous_day_progress.streak + 1
    else:
        return 1

def summarize_daily_progresses(daily_progresses: list[DailyProgress], types: list[str], db: Session):
    """
    Summarizes the provided DailyProgress entries into a single summary.
    """
    results = {
        "study_seconds": None,
        "total_videos_watched": None,
        "vocab_seen": None,
        "vocab_known": None,
        "streak": None
    }

    if "study_seconds" in types:
        results["study_seconds"] = sum(progress.study_seconds for progress in daily_progresses)
    if "total_videos_watched" in types:
        results["total_videos_watched"] = daily_progresses[-1].total_videos_watched if daily_progresses else 0
    if "vocab_seen" in types:
        results["vocab_seen"] = sum(progress.new_vocab_seen for progress in daily_progresses)
    if "vocab_known" in types:
        results["vocab_known"] = sum(progress.new_vocab_known for progress in daily_progresses)
    if "streak" in types:
        today_progress = next((progress for progress in daily_progresses if progress.day == date.today()), None)
        yesterday_progress = next((progress for progress in daily_progresses if progress.day == date.today() - timedelta(days=1)), None)
        results["streak"] = today_progress.streak if today_progress else (yesterday_progress.streak if yesterday_progress else 0)
    
    return results
