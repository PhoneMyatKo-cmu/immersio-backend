from math import ceil

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.base import get_db
from models.user import EstimatedLevel, User, UserRole
from schemas.user import (
    Message,
    UserAdminListResponse,
    UserAdminRead,
    UserRoleUpdate,
)
from services.auth.authentication_service import require_admin
from services.user.user_services import (
    change_user_role,
    get_user_by_id,
    get_users_admin,
    soft_delete_user,
)

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("/")
def list_users(
    search: str = None,
    role: UserRole | None = None,
    estimated_level: EstimatedLevel | None = None,
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserAdminListResponse:
    users, total = get_users_admin(
        db,
        search=search,
        role=role,
        estimated_level=estimated_level,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    return UserAdminListResponse(
        items=users,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if page_size else 0,
    )


@router.get("/{user_id}")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserAdminRead:
    user = get_user_by_id(user_id, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.patch("/{user_id}/role")
def update_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserAdminRead:
    if user_id == admin.id and payload.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own admin role",
        )
    user = change_user_role(user_id, payload.role, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.delete("/{user_id}")
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Message:
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )
    user = soft_delete_user(user_id, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return Message(detail="User deactivated successfully")
