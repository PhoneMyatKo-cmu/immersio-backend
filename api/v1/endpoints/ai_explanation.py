from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.auth import get_current_user
from db.base import get_db
from schemas.user import UserRead
from schemas.vocab_context import ContextRequest, ContextResponse
from services.ai_explanation_cache_service import (
    ServiceUnavailableError,
    get_context_explanation_from_ai,
)

router = APIRouter(prefix="/context-explanation")


@router.post("/")
def get_ai_explanation(
    contextRequest: ContextRequest,
    db: Session = Depends(get_db),
    current_user: UserRead = Depends(get_current_user),
) -> ContextResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthenticated"
        )
    print(contextRequest)
    try:
        explanation = get_context_explanation_from_ai(contextRequest, db)
        return explanation
    except ServiceUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=404, detail="Not Found")
