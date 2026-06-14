from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.user import EstimatedLevel, User, UserRole
from services.auth.authentication_service import verify_password
from services.user.user_services import (
    delete_user,
    get_user_by_email,
    save_user,
    update_user,
    update_user_password,
)

pytestmark = [pytest.mark.integration]


@pytest.fixture()
def user_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    User.__table__.create(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        User.__table__.drop(engine)
        engine.dispose()


def _user(
    email: str = "learner@example.com",
    first_name: str = "Test",
    last_name: str = "Learner",
    password_hash: str = "hashed-password",
) -> User:
    return User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=password_hash,
        estimated_level=EstimatedLevel.beginner,
        role=UserRole.LEARNER,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )


class _UserPatch:
    def __init__(self, **values):
        self.values = values

    def model_dump(self, exclude_unset=False):
        return self.values


def test_save_user_persists_and_refreshes_user(user_db):
    user = _user(email="new@example.com")

    saved = save_user(user, user_db)

    assert saved is user
    assert saved.id is not None
    assert (
        user_db.scalar(select(User).where(User.email == "new@example.com"))
        is saved
    )


def test_save_user_rolls_back_and_raises_conflict_for_duplicate_email(user_db):
    save_user(_user(email="dupe@example.com"), user_db)

    with pytest.raises(HTTPException) as exc_info:
        save_user(_user(email="dupe@example.com"), user_db)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "A user with this email already exists"
    assert user_db.query(User).filter(User.email == "dupe@example.com").count() == 1


def test_get_user_by_email_lowercases_lookup_email(user_db):
    user = save_user(_user(email="lower@example.com"), user_db)

    result = get_user_by_email("LOWER@EXAMPLE.COM", user_db)

    assert result is user


def test_get_user_by_email_returns_none_when_missing(user_db):
    assert get_user_by_email("missing@example.com", user_db) is None


def test_update_user_applies_model_dump_values(user_db):
    user = save_user(_user(email="update@example.com"), user_db)
    patch = _UserPatch(
        first_name="Updated",
        estimated_level=EstimatedLevel.advanced,
        role=UserRole.ADMIN,
    )

    updated = update_user(user, patch, user_db)

    assert updated is user
    assert updated.first_name == "Updated"
    assert updated.last_name == "Learner"
    assert updated.estimated_level == EstimatedLevel.advanced
    assert updated.role == UserRole.ADMIN


def test_update_user_rolls_back_and_raises_500_on_commit_failure():
    user = _user()
    patch = _UserPatch(first_name="Updated")

    class FailingDb:
        rolled_back = False
        refreshed = False

        def commit(self):
            raise RuntimeError("commit failed")

        def rollback(self):
            self.rolled_back = True

        def refresh(self, user):
            self.refreshed = True

    db = FailingDb()

    with pytest.raises(HTTPException) as exc_info:
        update_user(user, patch, db)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to update user"
    assert db.rolled_back is True
    assert db.refreshed is False


def test_delete_user_removes_user(user_db):
    user = save_user(_user(email="delete@example.com"), user_db)

    delete_user(user, user_db)

    assert get_user_by_email("delete@example.com", user_db) is None


def test_delete_user_rolls_back_and_raises_500_on_commit_failure():
    user = _user()

    class FailingDb:
        rolled_back = False
        deleted = None

        def delete(self, user):
            self.deleted = user

        def commit(self):
            raise RuntimeError("commit failed")

        def rollback(self):
            self.rolled_back = True

    db = FailingDb()

    with pytest.raises(HTTPException) as exc_info:
        delete_user(user, db)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to delete user"
    assert db.deleted is user
    assert db.rolled_back is True


def test_update_user_password_hashes_new_password(user_db):
    user = save_user(_user(email="password@example.com"), user_db)

    updated = update_user_password(user, "new-secret-password", user_db)

    assert updated is user
    assert updated.password_hash != "new-secret-password"
    assert verify_password("new-secret-password", updated.password_hash) is True
    assert verify_password("hashed-password", updated.password_hash) is False


def test_update_user_password_rolls_back_and_raises_500_on_commit_failure(
    monkeypatch,
):
    user = _user()
    monkeypatch.setattr(
        "services.auth.authentication_service.hash_password",
        lambda password: f"hashed:{password}",
    )

    class FailingDb:
        rolled_back = False
        refreshed = False

        def commit(self):
            raise RuntimeError("commit failed")

        def rollback(self):
            self.rolled_back = True

        def refresh(self, user):
            self.refreshed = True

    db = FailingDb()

    with pytest.raises(HTTPException) as exc_info:
        update_user_password(user, "new-password", db)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to update password"
    assert user.password_hash == "hashed:new-password"
    assert db.rolled_back is True
    assert db.refreshed is False
