from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
)
from sqlalchemy.orm import relationship

from src.db.postgres import Base

# Association Table for User <-> SkillTag Many-to-Many Relationship
user_skills = Table(
    "user_skills",
    Base.metadata,
    Column(
        "user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "skill_id",
        Integer,
        ForeignKey("skill_tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class User(Base):
    """
    User model representing an account in SkillSwarm with a teaching_credits balance.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    teaching_credits = Column(Integer, default=0, nullable=False)
    learning_style = Column(String, default="visual", nullable=False)

    # Relationship to SkillTags
    skills = relationship("SkillTag", secondary=user_skills, back_populates="users")
    fallacies_logged = relationship(
        "LogicalFallacyLog", back_populates="user", cascade="all, delete-orphan"
    )
    preferences = relationship(
        "UserPreference",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    received_feedback = relationship(
        "TutorFeedback",
        foreign_keys="[TutorFeedback.tutor_id]",
        back_populates="tutor",
        cascade="all, delete-orphan",
    )
    given_feedback = relationship(
        "TutorFeedback",
        foreign_keys="[TutorFeedback.student_id]",
        back_populates="student",
        cascade="all, delete-orphan",
    )
    mastery_tokens = relationship(
        "MasteryTokenLog",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sent_transfers = relationship(
        "CreditTransferLog",
        foreign_keys="[CreditTransferLog.sender_id]",
        back_populates="sender",
    )
    received_transfers = relationship(
        "CreditTransferLog",
        foreign_keys="[CreditTransferLog.receiver_id]",
        back_populates="receiver",
    )
    reasoning_scores = relationship(
        "ReasoningScoreLog",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserPreference(Base):
    """
    UserPreference model storing Sensory-Sensitive settings for a user.
    """

    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    animations_enabled = Column(Boolean, default=True)
    high_contrast_mode = Column(Boolean, default=False)
    reading_speed_default = Column(Float, default=1.0)

    user = relationship("User", back_populates="preferences")


class TutorFeedback(Base):
    """
    TutorFeedback model storing ratings and comments for a tutor session.
    """

    __tablename__ = "tutor_feedback"

    id = Column(Integer, primary_key=True, index=True)
    tutor_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    student_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    skill_tag = Column(String, nullable=False)
    rating = Column(Integer, nullable=False)  # e.g. 1-5 where 5 is Excellent
    comment = Column(String, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    tutor = relationship(
        "User", foreign_keys=[tutor_id], back_populates="received_feedback"
    )
    student = relationship(
        "User", foreign_keys=[student_id], back_populates="given_feedback"
    )


class SkillTag(Base):
    """
    SkillTag model representing granular skills/topics a user possesses (e.g., 'Derivatives', 'React.js').
    """

    __tablename__ = "skill_tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)

    # Relationship to Users
    users = relationship("User", secondary=user_skills, back_populates="skills")


class LogicalFallacyLog(Base):
    """
    Logs logical fallacies detected in student questions for teacher dashboard analytics.
    """

    __tablename__ = "logical_fallacy_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    fallacy_type = Column(String, nullable=False)
    context = Column(String, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship back to User
    user = relationship("User", back_populates="fallacies_logged")


class MasteryTokenLog(Base):
    """
    Records blockchain transactions representing a student's minted Mastery Token.
    """

    __tablename__ = "mastery_token_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    skill_tag = Column(String, nullable=False)
    transaction_hash = Column(String, unique=True, index=True, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship back to User
    user = relationship("User", back_populates="mastery_tokens")


class CreditTransferLog(Base):
    """
    Records blockchain transactions representing a transfer of EduCoins between a student and tutor.
    """

    __tablename__ = "credit_transfer_logs"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    receiver_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    amount = Column(Integer, nullable=False)
    transaction_hash = Column(String, unique=True, index=True, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    sender = relationship(
        "User", foreign_keys=[sender_id], back_populates="sent_transfers"
    )
    receiver = relationship(
        "User", foreign_keys=[receiver_id], back_populates="received_transfers"
    )


class ReasoningScoreLog(Base):
    """
    Tracks and builds a student's 'Reasoning Ability' score over time.
    """

    __tablename__ = "reasoning_score_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    reasoning_ability_score = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="reasoning_scores")
