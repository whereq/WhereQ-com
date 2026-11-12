from datetime import datetime
from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    locale: str = "en"
    theme: str = "dark"


class UserRead(BaseModel):
    id: int
    username: str
    email: EmailStr
    is_active: bool
    locale: str
    theme: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    username: str | None = None
    locale: str | None = None
    theme: str | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
