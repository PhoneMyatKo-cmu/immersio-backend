
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models.user import EstimatedLevel, User, UserRole
from schemas.user import UserUpdate



def save_user(user: User, db: Session) -> User:
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

def get_user_by_email(email: str, db: Session) -> User | None:
    return db.query(User).filter(User.email == email.lower()).first()


def get_user_by_id(user_id: int, db: Session) -> User | None:
    return db.get(User, user_id)


def get_users_admin(
    db: Session,
    search: str = None,
    role: UserRole | None = None,
    estimated_level: EstimatedLevel | None = None,
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """List users for admin with optional filters (None = don't filter).

    Returns (rows, total_count).
    """
    stmt = select(User).order_by(User.created_at.desc())

    if search:
        term = f"%{search}%"
        stmt = stmt.where(
            func.concat(User.first_name, " ", User.last_name).ilike(term)
            | User.email.ilike(term)
        )
    if role is not None:
        stmt = stmt.where(User.role == role)
    if estimated_level is not None:
        stmt = stmt.where(User.estimated_level == estimated_level)
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))

    rows = (
        db.execute(stmt.limit(page_size).offset((page - 1) * page_size)).scalars().all()
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    return rows, total


def soft_delete_user(user_id: int, db: Session) -> User | None:
    """Deactivate a user by setting is_active to False.

    Returns the updated user, or None if no user with that id exists.
    """
    user = get_user_by_id(user_id, db)
    if user is None:
        return None

    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


def change_user_role(user_id: int, role: UserRole, db: Session) -> User | None:
    """Set a user's role. Returns the updated user, or None if not found."""
    user = get_user_by_id(user_id, db)
    if user is None:
        return None

    user.role = role
    db.commit()
    db.refresh(user)
    return user

def update_user(current_user: User, updated_user: UserUpdate, db: Session) -> User:
    for field, value in updated_user.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        print(e)
        raise HTTPException(status_code=500, detail="Failed to update user") from e

    db.refresh(current_user)
    return current_user

def delete_user(user: User, db: Session):
    try:
        db.delete(user)
        db.commit()
    except Exception as e:
        db.rollback()
        print(e)
        raise HTTPException(status_code=500, detail="Failed to delete user") from e

def update_user_password(current_user: User, new_password: str, db: Session) -> User:
    from services.auth.authentication_service import hash_password
    current_user.password_hash = hash_password(new_password)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        print(e)
        raise HTTPException(status_code=500, detail="Failed to update password") from e

    db.refresh(current_user)
    return current_user