from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from jose import jwt

from services.auth import authentication_service as auth

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(auth, "ALGORITHM", "HS256")
    monkeypatch.setattr(auth, "ACCESS_TOKEN_EXPIRE_MINUTES", 15)
    monkeypatch.setattr(auth, "REFRESH_TOKEN_EXPIRE_DAYS", 7)
    auth._revoked_tokens.clear()
    yield
    auth._revoked_tokens.clear()


def test_hash_password_creates_verifiable_non_plaintext_hash():
    password = "correct-horse-battery"

    hashed = auth.hash_password(password)

    assert hashed != password
    assert hashed.startswith("$2")
    assert auth.verify_password(password, hashed) is True
    assert auth.verify_password("wrong-password", hashed) is False


def test_authenticate_user_returns_user_for_valid_credentials(monkeypatch):
    user = SimpleNamespace(
        email="learner@example.com",
        password_hash=auth.hash_password("secret-password"),
    )
    calls = []

    def fake_get_user_by_email(email, db):
        calls.append((email, db))
        return user

    monkeypatch.setattr(auth, "get_user_by_email", fake_get_user_by_email)
    db = object()

    result = auth.authenticate_user(db, "learner@example.com", "secret-password")

    assert result is user
    assert calls == [("learner@example.com", db)]


def test_authenticate_user_returns_none_for_missing_user(monkeypatch):
    monkeypatch.setattr(auth, "get_user_by_email", lambda email, db: None)

    result = auth.authenticate_user(object(), "missing@example.com", "password")

    assert result is None


def test_authenticate_user_returns_none_for_invalid_password(monkeypatch):
    user = SimpleNamespace(password_hash=auth.hash_password("real-password"))
    monkeypatch.setattr(auth, "get_user_by_email", lambda email, db: user)

    result = auth.authenticate_user(object(), "learner@example.com", "bad-password")

    assert result is None


def test_create_access_token_contains_expected_payload():
    token = auth.create_access_token("learner@example.com")

    payload = jwt.decode(token, "test-secret", algorithms=["HS256"])

    assert payload["sub"] == "learner@example.com"
    assert payload["type"] == auth.ACCESS_TOKEN_TYPE
    assert payload["jti"]
    assert datetime.fromtimestamp(payload["exp"], timezone.utc) > datetime.now(
        timezone.utc
    )


def test_create_token_pair_contains_access_and_refresh_tokens():
    tokens = auth.create_token_pair("learner@example.com")

    access_payload = jwt.decode(
        tokens["access_token"], "test-secret", algorithms=["HS256"]
    )
    refresh_payload = jwt.decode(
        tokens["refresh_token"], "test-secret", algorithms=["HS256"]
    )

    assert set(tokens) == {"access_token", "refresh_token"}
    assert access_payload["sub"] == "learner@example.com"
    assert access_payload["type"] == auth.ACCESS_TOKEN_TYPE
    assert refresh_payload["sub"] == "learner@example.com"
    assert refresh_payload["type"] == auth.REFRESH_TOKEN_TYPE


def test_decode_token_returns_token_payload_for_valid_access_token():
    token = auth.create_access_token("learner@example.com")

    token_data = auth.decode_token(
        token=token,
        expected_type=auth.ACCESS_TOKEN_TYPE,
        invalid_detail="invalid",
        expired_detail="expired",
    )

    assert token_data.sub == "learner@example.com"
    assert token_data.type == auth.ACCESS_TOKEN_TYPE
    assert token_data.jti


def test_decode_token_rejects_wrong_token_type():
    token = auth.create_refresh_token("learner@example.com")

    with pytest.raises(HTTPException) as exc_info:
        auth.decode_token(
            token=token,
            expected_type=auth.ACCESS_TOKEN_TYPE,
            invalid_detail="invalid token type",
            expired_detail="expired",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "invalid token type"
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


def test_decode_token_rejects_expired_token():
    token = auth.create_token(
        subject="learner@example.com",
        expires_delta=timedelta(seconds=-1),
        token_type=auth.ACCESS_TOKEN_TYPE,
    )

    with pytest.raises(HTTPException) as exc_info:
        auth.decode_token(
            token=token,
            expected_type=auth.ACCESS_TOKEN_TYPE,
            invalid_detail="invalid",
            expired_detail="access expired",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "access expired"


def test_revoke_token_prevents_future_decode():
    token = auth.create_access_token("learner@example.com")

    auth.revoke_token(token, expected_type=auth.ACCESS_TOKEN_TYPE)

    with pytest.raises(HTTPException) as exc_info:
        auth.decode_token(
            token=token,
            expected_type=auth.ACCESS_TOKEN_TYPE,
            invalid_detail="revoked or invalid",
            expired_detail="expired",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "revoked or invalid"


def test_clear_expired_revocations_removes_old_entries():
    auth._revoked_tokens["expired-token"] = datetime.now(timezone.utc) - timedelta(
        seconds=1
    )
    auth._revoked_tokens["active-token"] = datetime.now(timezone.utc) + timedelta(
        minutes=1
    )

    auth._clear_expired_revocations()

    assert auth._revoked_tokens == {
        "active-token": auth._revoked_tokens["active-token"]
    }


def test_get_current_user_returns_user_for_valid_access_token(monkeypatch):
    token = auth.create_access_token("learner@example.com")
    user = SimpleNamespace(email="learner@example.com")
    calls = []

    def fake_get_user_by_email(email, db):
        calls.append((email, db))
        return user

    monkeypatch.setattr(auth, "get_user_by_email", fake_get_user_by_email)
    db = object()

    result = auth.get_current_user(token=token, db=db)

    assert result is user
    assert calls == [("learner@example.com", db)]


def test_get_current_user_rejects_valid_token_for_missing_user(monkeypatch):
    token = auth.create_access_token("learner@example.com")
    monkeypatch.setattr(auth, "get_user_by_email", lambda email, db: None)

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(token=token, db=object())

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate credentials"


def test_get_user_from_refresh_token_returns_user(monkeypatch):
    token = auth.create_refresh_token("learner@example.com")
    user = SimpleNamespace(email="learner@example.com")
    monkeypatch.setattr(auth, "get_user_by_email", lambda email, db: user)

    result = auth.get_user_from_refresh_token(token, object())

    assert result is user


def test_get_user_from_refresh_token_rejects_access_token(monkeypatch):
    token = auth.create_access_token("learner@example.com")
    monkeypatch.setattr(auth, "get_user_by_email", lambda email, db: None)

    with pytest.raises(HTTPException) as exc_info:
        auth.get_user_from_refresh_token(token, object())

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate refresh token"
