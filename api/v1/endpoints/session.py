
from curl_cffi import Session
from fastapi import APIRouter, Depends

from db.base import get_db
from schemas.session import SessionData
from services.daily_progress.daily_progress_service import save_daily_progress
from services.session.session_service import save_learning_session
from services.user_vocab_exposure.user_vocab_exposure_service import save_user_vocab_exposure


router = APIRouter(prefix="/session")

@router.post("/")
def upload_data(
    session_data: SessionData,
    db: Session = Depends(get_db)
):
    
    print(f"Received session data for user {session_data.user_id}: {session_data}")

    learning_session = save_learning_session(session_data, db)
    save_user_vocab_exposure(learning_session, db)
    save_daily_progress(learning_session, db)
    return {"message": "Learning session data saved successfully.", "session_id": learning_session.id}


