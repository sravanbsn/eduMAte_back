from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class Token(BaseModel):
    model_config = ConfigDict(strict=True)
    access_token: str
    token_type: str


class TokenData(BaseModel):
    model_config = ConfigDict(strict=True)
    username: Optional[str] = None


class SkillTagBase(BaseModel):
    model_config = ConfigDict(strict=True)
    name: str
    description: Optional[str] = None


class SkillTagCreate(SkillTagBase):
    pass


class SkillTagResponse(SkillTagBase):
    id: int

    model_config = ConfigDict(from_attributes=True, strict=True)


class UserBase(BaseModel):
    model_config = ConfigDict(strict=True)
    username: str
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserResponse(UserBase):
    id: int
    teaching_credits: int
    skills: List[SkillTagResponse] = []

    model_config = ConfigDict(from_attributes=True, strict=True)


class SocraticRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    question: str
    concept_name: str
    persona: Optional[str] = None


class SocraticResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    reply: str


class AdaptaRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    text: Optional[str] = None
    url: Optional[str] = None


class AdaptaResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    original_text: str
    bionic_text: str
    analogies: Dict[str, str]


class UserPreferenceUpdate(BaseModel):
    model_config = ConfigDict(strict=True)
    animations_enabled: Optional[bool] = None
    high_contrast_mode: Optional[bool] = None
    reading_speed_default: Optional[float] = None


class UserPreferenceResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    animations_enabled: bool
    high_contrast_mode: bool
    reading_speed_default: float


class TTSRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    text: str
    reading_speed: float = 1.0


class SyllabusParseRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    text: str


class TaskBlock(BaseModel):
    model_config = ConfigDict(strict=True)
    topic: str
    deadline: Optional[str] = None
    description: str


class VisualTaskBreakdownResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    tasks: List[TaskBlock]


class WebhookTransactionPayload(BaseModel):
    model_config = ConfigDict(strict=True)
    user_id: int
    skill_tag: str
    transaction_hash: str
    security_hash: str


class TeacherExportResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    user_id: int
    concept_name: str
    summary_report: str


class TutorFeedbackCreate(BaseModel):
    model_config = ConfigDict(strict=True)
    skill_tag: str
    rating: int
    comment: Optional[str] = None


class TutorFeedbackResponse(BaseModel):
    id: int
    tutor_id: int
    student_id: int
    skill_tag: str
    rating: int
    comment: Optional[str] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True, strict=True)


class CreditTransferResponse(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    amount: int
    transaction_hash: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True, strict=True)


class MasteryTokenResponse(BaseModel):
    id: int
    user_id: int
    skill_tag: str
    transaction_hash: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True, strict=True)


class LogicalFallacyResponse(BaseModel):
    id: int
    user_id: int
    fallacy_type: str
    context: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True, strict=True)
