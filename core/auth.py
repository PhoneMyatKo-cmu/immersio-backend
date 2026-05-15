from datetime import datetime, timedelta, timezone
from uuid import uuid4

from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError
from dotenv import load_dotenv
import bcrypt
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy import select
from schemas.user import *
from models.user import User
from db.base import get_db
from sqlalchemy.orm import Session
import os

load_dotenv()
SECRET_KEY = os.getenv("SECURITY_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(str(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")))
REFRESH_TOKEN_EXPIRE_DAYS = int(str(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS")))
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
_revoked_tokens: dict[str, datetime] = {}

# hash password
def hash_password(password: str):
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

# verify password
def verify_password(plain, hashed):
    return bcrypt.checkpw(
        plain.encode('utf-8'),
        hashed.encode('utf-8')
    )

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


def create_token(subject: str, expires_delta: timedelta, token_type: str) -> str:
    expires_at = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": subject,
        "type": token_type,
        "exp": expires_at,
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(subject: str) -> str:
    return create_token(
        subject=subject,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type=ACCESS_TOKEN_TYPE,
    )

def authenticate_user(db: Session, email: str, password: str) -> UserRead | None:
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user

def create_refresh_token(subject: str) -> str:
    return create_token(
        subject=subject,
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        token_type=REFRESH_TOKEN_TYPE,
    )

def create_token_pair(subject: str) -> dict[str, str]:
    return {
        "access_token": create_access_token(subject),
        "refresh_token": create_refresh_token(subject),
    }

def get_user_by_email(db: Session, email: str) -> UserRead | None:
    return db.scalar(select(User).where(User.email == email.lower()))

def _credentials_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )

def _token_expiration(payload: dict) -> datetime:
    exp = payload.get("exp")
    if isinstance(exp, datetime):
        return exp
    if isinstance(exp, (int, float)):
        return datetime.fromtimestamp(exp, timezone.utc)
    raise ValueError("Token is missing expiration")

def _token_revocation_key(token: str, payload: dict) -> str:
    return str(payload.get("jti") or token)

def _token_revocation_key_from_data(token: str, token_data: TokenPayload) -> str:
    return str(token_data.jti or token)

def _clear_expired_revocations() -> None:
    now = datetime.now(timezone.utc)
    for token_key, expires_at in list(_revoked_tokens.items()):
        if expires_at <= now:
            del _revoked_tokens[token_key]

def _is_token_revoked(token: str, payload: dict) -> bool:
    _clear_expired_revocations()
    return _token_revocation_key(token, payload) in _revoked_tokens

def decode_token(
    token: str,
    expected_type: str,
    invalid_detail: str,
    expired_detail: str,
) -> TokenPayload:
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        token_data = TokenPayload(
            sub=payload.get("sub"),
            type=payload.get("type"),
            exp=_token_expiration(payload),
            jti=payload.get("jti"),
        )
    except ExpiredSignatureError:
        raise _credentials_error(expired_detail) from None
    except (JWTError, ValidationError, ValueError):
        raise _credentials_error(invalid_detail) from None

    if token_data.type != expected_type or _is_token_revoked(token, payload):
        raise _credentials_error(invalid_detail)

    return token_data

def revoke_token(
    token: str,
    expected_type: str,
    invalid_detail: str = "Could not validate token",
    expired_detail: str = "Token has expired",
) -> None:
    token_data = decode_token(
        token=token,
        expected_type=expected_type,
        invalid_detail=invalid_detail,
        expired_detail=expired_detail,
    )
    _revoked_tokens[_token_revocation_key_from_data(token, token_data)] = token_data.exp

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UserRead:
    token_data = decode_token(
        token=token,
        expected_type=ACCESS_TOKEN_TYPE,
        invalid_detail="Could not validate credentials",
        expired_detail="Access token has expired",
    )

    user = get_user_by_email(db, token_data.sub)
    if user is None:
        raise _credentials_error("Could not validate credentials")
    return user

def get_user_from_refresh_token(refresh_token: str, db: Session) -> User:
    token_data = decode_token(
        token=refresh_token,
        expected_type=REFRESH_TOKEN_TYPE,
        invalid_detail="Could not validate refresh token",
        expired_detail="Refresh token has expired",
    )

    user = get_user_by_email(db, token_data.sub)
    if user is None:
        raise _credentials_error("Could not validate refresh token")
    return user
