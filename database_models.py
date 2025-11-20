from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    """
    User model for storing user account information.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_paid_user = Column(Boolean, default=False, nullable=False)
    trial_start_date = Column(String, nullable=True)
    last_release_timestamp = Column(String, nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    stripe_price_id = Column(String, nullable=True)
    subscription_status = Column(String, default="trial", nullable=True)
    
    # Relationship for one-to-many linking (User to Project)
    projects = relationship("Project", back_populates="owner")


class Project(Base):
    """
    Project model for storing user project information.
    """
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship back to User
    owner = relationship("User", back_populates="projects")

