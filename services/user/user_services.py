
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models.user import User



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

def update_user(current_user: User, updated_user: User, db: Session) -> User:
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