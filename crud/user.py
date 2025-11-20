"""
UserRepository for database operations on User model
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database_models import User


class UserRepository:
    """
    Repository class for User database operations.
    Encapsulates all database logic for the User model.
    """
    
    def __init__(self, db: AsyncSession):
        """
        Initialize the repository with a database session.
        
        Args:
            db: AsyncSession instance for database operations
        """
        self.db = db
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Retrieve a user by email address.
        
        Args:
            email: User's email address (case-insensitive search)
            
        Returns:
            User object if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Retrieve a user by ID.
        
        Args:
            user_id: User's ID
            
        Returns:
            User object if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def create_user(self, user_data: dict) -> User:
        """
        Create a new user in the database.
        
        Args:
            user_data: Dictionary containing user data. Must include:
                - email: str
                - hashed_password: str
                Optional:
                - is_active: bool (defaults to True)
                - is_paid_user: bool (defaults to False)
                - trial_start_date: str (optional)
                
        Returns:
            Created User object
        """
        user = User(
            email=user_data["email"].lower(),
            hashed_password=user_data["hashed_password"],
            is_active=user_data.get("is_active", True),
            is_paid_user=user_data.get("is_paid_user", False),
            trial_start_date=user_data.get("trial_start_date")
        )
        self.db.add(user)
        await self.db.flush()  # Flush to get the ID without committing
        await self.db.refresh(user)  # Refresh to get the generated ID
        return user
    
    async def update_user(self, user: User, updates: dict) -> User:
        """
        Update user fields.
        
        Args:
            user: User object to update
            updates: Dictionary of fields to update (e.g., {"is_paid_user": True})
            
        Returns:
            Updated User object
        """
        for key, value in updates.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        await self.db.flush()
        await self.db.refresh(user)
        return user

