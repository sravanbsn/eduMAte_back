from sqlalchemy import Column, Integer, String, Table, ForeignKey
from sqlalchemy.orm import relationship
from src.db.postgres import Base

# Association Table for User <-> SkillTag Many-to-Many Relationship
user_skills = Table(
    'user_skills',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete="CASCADE"), primary_key=True),
    Column('skill_id', Integer, ForeignKey('skill_tags.id', ondelete="CASCADE"), primary_key=True)
)

class User(Base):
    """
    User model representing an account in SkillSwarm with a teaching_credits balance.
    """
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    teaching_credits = Column(Integer, default=0, nullable=False)
    
    # Relationship to SkillTags
    skills = relationship("SkillTag", secondary=user_skills, back_populates="users")


class SkillTag(Base):
    """
    SkillTag model representing granular skills/topics a user possesses (e.g., 'Derivatives', 'React.js').
    """
    __tablename__ = 'skill_tags'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)

    # Relationship to Users
    users = relationship("User", secondary=user_skills, back_populates="skills")
