"""
Admin Tools - Temporary endpoint for user deletion
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from database_models import User

# Create router with /internal prefix
admin_router = APIRouter(prefix="/internal", tags=["admin"])


class DeleteUserRequest(BaseModel):
    email: str


@admin_router.post("/delete-user")
async def delete_user(
    request: DeleteUserRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a user by email from the database.
    Temporary admin-only endpoint for cleanup.
    """
    # Query user by email
    result = await db.execute(
        select(User).where(User.email == request.email)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=404,
            detail=f"User with email {request.email} not found"
        )
    
    # Delete the user
    db.delete(user)
    await db.commit()
    
    return {
        "ok": True,
        "message": f"User with email {request.email} deleted successfully"
    }

