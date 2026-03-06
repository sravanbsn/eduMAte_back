from pydantic import BaseModel, ConfigDict


class SessionCompleteRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    student_id: int
    tutor_id: int


class TutorRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    skill_name: str
    student_id: int


class SessionFeedbackRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    student_id: int
    tutor_id: int
    skill_name: str
    rating: int
    transcript: str
