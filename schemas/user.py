from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from models.user import EstimatedLevel, UserRole


class UserCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    estimated_level: EstimatedLevel = EstimatedLevel.beginner
    role: UserRole = UserRole.LEARNER

    @field_validator("password")
    @classmethod
    def password_must_fit_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 bytes or fewer")
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("password")
    @classmethod
    def password_must_fit_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 bytes or fewer")
        return value


class UserRead(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: EmailStr
    estimated_level: EstimatedLevel
    role: UserRole
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    # Self-service profile update. Deliberately excludes `role` (privilege
    # escalation — only an admin may change roles) and `email` (it is the JWT
    # subject/identity, changing it would invalidate live tokens).
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    estimated_level: EstimatedLevel | None = None


class UserAdminRead(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: EmailStr
    estimated_level: EstimatedLevel
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class UserAdminListResponse(BaseModel):
    items: list[UserAdminRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class UserRoleUpdate(BaseModel):
    role: UserRole


class RoleBreakdown(BaseModel):
    admin: int
    learner: int


class LevelBreakdown(BaseModel):
    beginner: int
    intermediate: int
    advanced: int


class UserStatsResponse(BaseModel):
    total: int
    active: int
    inactive: int
    # by_role: RoleBreakdown
    by_level: LevelBreakdown
    signups_last_7_days: int
    signups_last_30_days: int
    active_last_7_days: int
    active_last_30_days: int


class UserUpdatePassword(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("current_password", "new_password")
    @classmethod
    def password_must_fit_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 bytes or fewer")
        return value


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str
    type: str
    exp: datetime
    jti: str | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, min_length=1)


class Message(BaseModel):
    detail: str
