from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime
from database import Base


class Project(Base):
    """
    Project model for storing project information.
    Anonymous projects (no user association).
    """
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

