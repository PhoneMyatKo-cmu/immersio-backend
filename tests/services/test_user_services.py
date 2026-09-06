from datetime import datetime, timedelta

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
    get_user_stats,
    get_users_admin,
    save_user,
    soft_delete_user,
    update_user,
    update_user_password,
)

pytestmark = [pytest.mark.integration]


@pytest.fixture()
def user_db():
    # TEMPORARY: User.added_videos now references Video, which in turn references
    # Caption/ShadowingSentence/etc. Import the full model graph so SQLAlchemy can
    # resolve those string relationships when it configures the mappers. Only the
    # non-JSONB tables we actually use (users, videos) are created — SQLite can't
    # build the JSONB tables, which is why the rest stay import-only.
    import models.user            # noqa: F401
    import models.video           # noqa: F401
    import models.vocab           # noqa: F401
    import models.processed_caption   # noqa: F401
    import models.sentence        # noqa: F401
    import models.video_vocab_profile  # noqa: F401
    import models.user_vocab_profile   # noqa: F401
    import models.user_vocab_library   # noqa: F401
    import models.ai_explanation_cache  # noqa: F401
    from models.video import Video

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    User.__table__.create(engine)
    Video.__table__.create(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Video.__table__.drop(engine)
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
    assert user_db.scalar(select(User).where(User.email == "new@example.com")) is saved


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


def test_delete_user_removes_user(db_session):
    # Uses the shared Postgres test-DB fixture so the full schema exists:
    # delete_user lazy-loads the user_saved_vocabulary / user_vocab_profile
    # backrefs, which the single-table SQLite fixture cannot satisfy.
    user = save_user(_user(email="delete@example.com"), db_session)

    delete_user(user, db_session)

    assert get_user_by_email("delete@example.com", db_session) is None


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


# Test get_user_admin
#
# These exercise get_users_admin end-to-end and must run on the Postgres
# db_session fixture: the search branch uses func.concat, which SQLite (the
# user_db fixture) cannot execute.


def _seed_user(
    db,
    email,
    first_name="Test",
    last_name="Learner",
    role=UserRole.LEARNER,
    estimated_level=EstimatedLevel.beginner,
    is_active=True,
    created_at=datetime(2026, 1, 1, 12, 0, 0),
    last_login_at=None,
) -> User:
    user = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash="hashed-password",
        role=role,
        estimated_level=estimated_level,
        is_active=is_active,
        created_at=created_at,
        last_login_at=last_login_at,
    )
    return save_user(user, db)


def _emails(rows) -> set[str]:
    return {u.email for u in rows}


# --- baseline / no filters ---------------------------------------------------


def test_get_users_admin_returns_all_when_no_filters(db_session):
    _seed_user(db_session, email="a@example.com")
    _seed_user(db_session, email="b@example.com")

    rows, total = get_users_admin(db_session)

    assert total == 2
    assert _emails(rows) == {"a@example.com", "b@example.com"}


def test_get_users_admin_empty_db_returns_empty(db_session):
    rows, total = get_users_admin(db_session)

    assert rows == []
    assert total == 0


def test_get_users_admin_orders_by_created_at_desc(db_session):
    _seed_user(db_session, email="old@example.com", created_at=datetime(2026, 1, 1))
    _seed_user(db_session, email="new@example.com", created_at=datetime(2026, 1, 3))
    _seed_user(db_session, email="mid@example.com", created_at=datetime(2026, 1, 2))

    rows, _ = get_users_admin(db_session)

    assert [u.email for u in rows] == [
        "new@example.com",
        "mid@example.com",
        "old@example.com",
    ]


# --- search ------------------------------------------------------------------


def test_get_users_admin_search_matches_full_name(db_session):
    _seed_user(db_session, email="aya@example.com", first_name="Aya", last_name="Tanaka")
    _seed_user(db_session, email="bob@example.com", first_name="Bob", last_name="Smith")

    rows, total = get_users_admin(db_session, search="tan")

    assert total == 1
    assert _emails(rows) == {"aya@example.com"}


def test_get_users_admin_search_matches_across_name_space(db_session):
    _seed_user(db_session, email="aya@example.com", first_name="Aya", last_name="Tanaka")

    rows, total = get_users_admin(db_session, search="aya tan")

    assert total == 1
    assert _emails(rows) == {"aya@example.com"}


def test_get_users_admin_search_matches_email(db_session):
    _seed_user(db_session, email="aya@example.com", first_name="Aya", last_name="Tanaka")
    _seed_user(db_session, email="bob@example.com", first_name="Bob", last_name="Smith")

    rows, total = get_users_admin(db_session, search="aya@")

    assert total == 1
    assert _emails(rows) == {"aya@example.com"}


def test_get_users_admin_search_matches_name_or_email_union(db_session):
    # matched by NAME
    _seed_user(db_session, email="one@example.com", first_name="Aya", last_name="Tanaka")
    # matched by EMAIL
    _seed_user(db_session, email="tanaka@example.com", first_name="Bob", last_name="Smith")
    # unrelated
    _seed_user(db_session, email="none@example.com", first_name="Ken", last_name="Watts")

    rows, total = get_users_admin(db_session, search="tanaka")

    assert total == 2
    assert _emails(rows) == {"one@example.com", "tanaka@example.com"}


def test_get_users_admin_search_is_case_insensitive(db_session):
    _seed_user(db_session, email="aya@example.com", first_name="Aya", last_name="Tanaka")

    rows, total = get_users_admin(db_session, search="TANAKA")

    assert total == 1
    assert _emails(rows) == {"aya@example.com"}


def test_get_users_admin_search_no_match_returns_empty(db_session):
    _seed_user(db_session, email="aya@example.com", first_name="Aya", last_name="Tanaka")

    rows, total = get_users_admin(db_session, search="zzz")

    assert rows == []
    assert total == 0


def test_get_users_admin_empty_search_returns_all(db_session):
    _seed_user(db_session, email="a@example.com")
    _seed_user(db_session, email="b@example.com")

    rows, total = get_users_admin(db_session, search="")

    assert total == 2


# --- equality filters --------------------------------------------------------


def test_get_users_admin_filters_by_role(db_session):
    _seed_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    _seed_user(db_session, email="learner@example.com", role=UserRole.LEARNER)

    rows, total = get_users_admin(db_session, role=UserRole.ADMIN)

    assert total == 1
    assert _emails(rows) == {"admin@example.com"}


def test_get_users_admin_filters_by_estimated_level(db_session):
    _seed_user(db_session, email="beg@example.com", estimated_level=EstimatedLevel.beginner)
    _seed_user(db_session, email="adv@example.com", estimated_level=EstimatedLevel.advanced)

    rows, total = get_users_admin(db_session, estimated_level=EstimatedLevel.advanced)

    assert total == 1
    assert _emails(rows) == {"adv@example.com"}


def test_get_users_admin_filter_is_active_true(db_session):
    _seed_user(db_session, email="active@example.com", is_active=True)
    _seed_user(db_session, email="inactive@example.com", is_active=False)

    rows, total = get_users_admin(db_session, is_active=True)

    assert total == 1
    assert _emails(rows) == {"active@example.com"}


def test_get_users_admin_filter_is_active_false(db_session):
    _seed_user(db_session, email="active@example.com", is_active=True)
    _seed_user(db_session, email="inactive@example.com", is_active=False)

    rows, total = get_users_admin(db_session, is_active=False)

    assert total == 1
    assert _emails(rows) == {"inactive@example.com"}


def test_get_users_admin_filter_is_active_none_returns_both(db_session):
    _seed_user(db_session, email="active@example.com", is_active=True)
    _seed_user(db_session, email="inactive@example.com", is_active=False)

    rows, total = get_users_admin(db_session, is_active=None)

    assert total == 2
    assert _emails(rows) == {"active@example.com", "inactive@example.com"}


def test_get_users_admin_combined_filters_use_and_semantics(db_session):
    # matches all three conditions
    _seed_user(
        db_session,
        email="match@example.com",
        first_name="Aya",
        last_name="Tanaka",
        role=UserRole.LEARNER,
        is_active=True,
    )
    # right name+role but INACTIVE -> excluded
    _seed_user(
        db_session,
        email="inactive@example.com",
        first_name="Aya",
        last_name="Tanaka",
        role=UserRole.LEARNER,
        is_active=False,
    )
    # right name+active but ADMIN -> excluded
    _seed_user(
        db_session,
        email="admin@example.com",
        first_name="Aya",
        last_name="Tanaka",
        role=UserRole.ADMIN,
        is_active=True,
    )

    rows, total = get_users_admin(
        db_session, search="tanaka", role=UserRole.LEARNER, is_active=True
    )

    assert total == 1
    assert _emails(rows) == {"match@example.com"}


# --- pagination --------------------------------------------------------------


def _seed_five_ordered(db):
    # created_at ascending by day; newest = day 5
    for day in range(1, 6):
        _seed_user(db, email=f"u{day}@example.com", created_at=datetime(2026, 1, day))


def test_get_users_admin_pagination_limits_rows(db_session):
    _seed_five_ordered(db_session)

    rows, total = get_users_admin(db_session, page=1, page_size=2)

    assert total == 5
    assert [u.email for u in rows] == ["u5@example.com", "u4@example.com"]


def test_get_users_admin_pagination_offsets_page(db_session):
    _seed_five_ordered(db_session)

    rows, total = get_users_admin(db_session, page=2, page_size=2)

    assert total == 5
    assert [u.email for u in rows] == ["u3@example.com", "u2@example.com"]


def test_get_users_admin_pagination_last_partial_page(db_session):
    _seed_five_ordered(db_session)

    rows, total = get_users_admin(db_session, page=3, page_size=2)

    assert total == 5
    assert [u.email for u in rows] == ["u1@example.com"]


def test_get_users_admin_page_beyond_range_returns_empty_but_total_full(db_session):
    _seed_five_ordered(db_session)

    rows, total = get_users_admin(db_session, page=99, page_size=2)

    assert rows == []
    assert total == 5


def test_get_users_admin_total_reflects_filters_not_page(db_session):
    _seed_user(db_session, email="a1@example.com", role=UserRole.ADMIN)
    _seed_user(db_session, email="a2@example.com", role=UserRole.ADMIN)
    _seed_user(db_session, email="a3@example.com", role=UserRole.ADMIN)
    _seed_user(db_session, email="l1@example.com", role=UserRole.LEARNER)

    rows, total = get_users_admin(
        db_session, role=UserRole.ADMIN, page=1, page_size=2
    )

    # total counts the filtered set (3 admins), not the page (2 rows)
    assert total == 3
    assert len(rows) == 2


# Test get_user_stats
#
# get_user_stats is LEARNER-scoped: every metric filters role == LEARNER, so
# admins are excluded from all counts. These run on Postgres db_session.


def test_get_user_stats_empty_db(db_session):
    stats = get_user_stats(db_session)

    assert stats["total"] == 0
    assert stats["active"] == 0
    assert stats["inactive"] == 0
    assert stats["by_level"] == {"beginner": 0, "intermediate": 0, "advanced": 0}
    assert stats["signups_last_7_days"] == 0
    assert stats["signups_last_30_days"] == 0
    assert stats["active_last_7_days"] == 0
    assert stats["active_last_30_days"] == 0


def test_get_user_stats_counts_and_learner_scoping(db_session):
    # 3 learners (2 active, 1 inactive)
    _seed_user(db_session, email="l1@example.com", role=UserRole.LEARNER, is_active=True)
    _seed_user(db_session, email="l2@example.com", role=UserRole.LEARNER, is_active=True)
    _seed_user(db_session, email="l3@example.com", role=UserRole.LEARNER, is_active=False)
    # 2 admins (must be excluded from every count)
    _seed_user(db_session, email="a1@example.com", role=UserRole.ADMIN, is_active=True)
    _seed_user(db_session, email="a2@example.com", role=UserRole.ADMIN, is_active=False)

    stats = get_user_stats(db_session)

    assert stats["total"] == 3        # learners only; inactive learner still counts
    assert stats["active"] == 2
    assert stats["inactive"] == 1


def test_get_user_stats_by_level(db_session):
    _seed_user(
        db_session, email="b1@example.com",
        estimated_level=EstimatedLevel.beginner, is_active=True,
    )
    _seed_user(
        db_session, email="b2@example.com",
        estimated_level=EstimatedLevel.beginner, is_active=False,  # inactive still counts
    )
    _seed_user(
        db_session, email="i1@example.com",
        estimated_level=EstimatedLevel.intermediate,
    )
    # advanced belongs to an ADMIN -> excluded, so advanced stays 0
    _seed_user(
        db_session, email="adv-admin@example.com",
        role=UserRole.ADMIN, estimated_level=EstimatedLevel.advanced,
    )

    stats = get_user_stats(db_session)

    assert stats["by_level"] == {"beginner": 2, "intermediate": 1, "advanced": 0}


def test_get_user_stats_time_windows(db_session):
    now = datetime.utcnow()

    # signups: created_at recency
    _seed_user(db_session, email="s3d@example.com", created_at=now - timedelta(days=3))
    _seed_user(db_session, email="s10d@example.com", created_at=now - timedelta(days=10))
    _seed_user(db_session, email="s40d@example.com", created_at=now - timedelta(days=40))

    # logins: last_login_at recency (created long ago so they don't affect signups)
    old = now - timedelta(days=200)
    _seed_user(
        db_session, email="log3d@example.com",
        created_at=old, last_login_at=now - timedelta(days=3),
    )
    _seed_user(
        db_session, email="log10d@example.com",
        created_at=old, last_login_at=now - timedelta(days=10),
    )
    _seed_user(
        db_session, email="lognever@example.com",
        created_at=old, last_login_at=None,  # never logged in -> excluded
    )
    # recent admin -> excluded from both signup and login windows
    _seed_user(
        db_session, email="admin-recent@example.com",
        role=UserRole.ADMIN, created_at=now, last_login_at=now,
    )

    stats = get_user_stats(db_session)

    # signups: 3d in both; 10d in 30 only; 40d in neither. (login-only learners
    # were created 200d ago, so they never enter the signup windows.)
    assert stats["signups_last_7_days"] == 1
    assert stats["signups_last_30_days"] == 2
    # active: 3d in both; 10d in 30 only; null and 200d-created signup users
    # (no last_login) excluded.
    assert stats["active_last_7_days"] == 1
    assert stats["active_last_30_days"] == 2


# Test soft_delete_user


def test_soft_delete_user_returns_none_when_missing(db_session):
    assert soft_delete_user(999, db_session) is None


def test_soft_delete_user_deactivates_active_user(db_session):
    user = _seed_user(db_session, email="active@example.com", is_active=True)

    result = soft_delete_user(user.id, db_session)

    assert result is user
    assert result.is_active is False
    # persisted, not just in-memory
    assert get_user_by_email("active@example.com", db_session).is_active is False


def test_soft_delete_user_is_idempotent_for_inactive_user(db_session):
    user = _seed_user(db_session, email="inactive@example.com", is_active=False)

    result = soft_delete_user(user.id, db_session)

    assert result is user
    assert result.is_active is False
