from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.base import get_db
from schemas.vocab_context import ContextRequest, ContextResponse
from services.ai_explanation_cache_service import (
    ServiceUnavailableError,
    get_context_explanation_from_ai,
)

router = APIRouter(prefix="/context-explanation")


@router.post("/")
def get_ai_explanation(
    contextRequest: ContextRequest, db: Session = Depends(get_db)
) -> ContextResponse:

    try:
        explanation = get_context_explanation_from_ai(contextRequest, db)
        return explanation
    except ServiceUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=404, detail="Not Found")
