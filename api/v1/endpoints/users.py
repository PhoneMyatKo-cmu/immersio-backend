from fastapi import Depends, APIRouter, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.auth import (
    ACCESS_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    authenticate_user,
    create_token_pair,
    get_current_user,
    get_user_from_refresh_token,
    hash_password,
    oauth2_scheme,
    revoke_token,
)
from db.base import get_db
from schemas.user import (
    LogoutRequest,
    Message,
    RefreshTokenRequest,
    Token,
    UserCreate,
    UserLogin,
    UserRead,
)
from models.user import User

router = APIRouter()

@router.post("/auth/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    user = User(
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        estimated_level=payload.estimated_level,
    )
    db.add(user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        ) from None

    db.refresh(user)
    return user


@router.post("/auth/login", response_model=Token)
def login_user(payload: UserLogin, db: Session = Depends(get_db)) -> Token:
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(**create_token_pair(user.email))


@router.post("/auth/token", response_model=Token)
def issue_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    user = authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(**create_token_pair(user.email))


@router.post("/auth/refresh", response_model=Token)
def refresh_access_token(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> Token:
    user = get_user_from_refresh_token(payload.refresh_token, db)
    revoke_token(
        token=payload.refresh_token,
        expected_type=REFRESH_TOKEN_TYPE,
        invalid_detail="Could not validate refresh token",
        expired_detail="Refresh token has expired",
    )
    return Token(**create_token_pair(user.email))


@router.post("/auth/logout", response_model=Message)
def logout_user(
    payload: LogoutRequest | None = None,
    access_token: str = Depends(oauth2_scheme),
) -> Message:
    revoke_token(
        token=access_token,
        expected_type=ACCESS_TOKEN_TYPE,
        invalid_detail="Could not validate credentials",
        expired_detail="Access token has expired",
    )
    if payload is not None and payload.refresh_token is not None:
        revoke_token(
            token=payload.refresh_token,
            expected_type=REFRESH_TOKEN_TYPE,
            invalid_detail="Could not validate refresh token",
            expired_detail="Refresh token has expired",
        )
    return Message(detail="Logged out successfully")


@router.get("/auth/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
