from pydantic import BaseModel, EmailStr
from typing import Optional, List

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class SkillTagBase(BaseModel):
    name: str
    description: Optional[str] = None

class SkillTagCreate(SkillTagBase):
    pass

class SkillTagResponse(SkillTagBase):
    id: int

    model_config = {"from_attributes": True}

class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    teaching_credits: int
    skills: List[SkillTagResponse] = []

    model_config = {"from_attributes": True}
