import os
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.api.v1.endpoints.webhooks import logger
from src.core.config import settings
from src.core.security import create_access_token, get_current_active_user
from src.db.postgres import get_db
from src.models.postgres import SkillTag, User
from src.models.schemas import Token, UserResponse

router = APIRouter()


class GoogleLoginRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    token: str


class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(strict=True)
    interests: Optional[str] = None
    skill_level: Optional[str] = None
    skills: Optional[List[str]] = None


async def verify_google_token(token: str) -> dict:
    """
    Verifies the Google ID token with Google's API.
    In a real app, use google-auth library, but httpx is fine for this demonstration.
    """
    if not settings.GOOGLE_CLIENT_ID:
        # Fallback for dev/mock if no client ID is set
        return {
            "email": f"mock_{token[:5]}@gmail.com",
            "name": f"Mock User {token[:5]}",
            "sub": f"google_{token[:5]}",
        }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
        )
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google Token",
            )
        data = response.json()
        if data["aud"] != settings.GOOGLE_CLIENT_ID:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token audience mismatch",
            )
        return data


@router.post("/google-login", response_model=Token)
async def google_login(
    request: GoogleLoginRequest, db: AsyncSession = Depends(get_db)
) -> Token:
    """
    Google Sign-In verification. Returns JWT token.
    """
    try:
        google_data = await verify_google_token(request.token)
        email = google_data["email"].lower()
        username = google_data.get("name", f"user_{google_data['sub'][:10]}")

        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        user = result.scalars().first()

        if not user:
            user = User(
                username=username,
                email=email,
                teaching_credits=5,
                interests="",
                skill_level="beginner",
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        access_token = create_access_token(data={"sub": user.username})
        return Token(access_token=access_token, token_type="bearer")
    except Exception as e:
        logger.error(f"Google Login Failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed"
        )


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    profile_data: UserProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Profile creation/updating for Skills, Interests, and Levels.
    """
    if profile_data.interests is not None:
        current_user.interests = profile_data.interests
    if profile_data.skill_level is not None:
        current_user.skill_level = profile_data.skill_level

    skills_list = profile_data.skills
    if skills_list is not None:
        current_user.skills.clear()
        for skill_name in skills_list:
            stmt = select(SkillTag).where(SkillTag.name == skill_name)
            res = await db.execute(stmt)
            skill = res.scalars().first()
            if not skill:
                skill = SkillTag(name=skill_name, description=f"Skill: {skill_name}")
                db.add(skill)
            current_user.skills.append(skill)

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user
