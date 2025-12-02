from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator

from config.settings import settings, IS_PRODUCTION

# Validate production database configuration
if IS_PRODUCTION:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL must be set in production. SQLite is not allowed in production.")
    if "sqlite" in settings.database_url.lower():
        raise RuntimeError("SQLite is forbidden in production. Use a PostgreSQL DATABASE_URL.")

# Default to SQLite with aiosqlite, but allow override via DATABASE_URL env var
DATABASE_URL = settings.database_url or "sqlite+aiosqlite:///./sql_app.db"

# Force SQLAlchemy to use psycopg2 sync driver safely inside async engine
sync_url = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://")

# Create async engine
engine = create_async_engine(
    sync_url,
    echo=False,
    future=True,
)

# Create declarative base for models
Base = declarative_base()

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db():
    """
    Initialize the database by creating all tables.
    This should be called on application startup.
    """
    async with engine.begin() as conn:
        # Import models here to ensure they're registered with Base
        from database_models import Project  # noqa: F401
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function that yields a database session.
    Use this in FastAPI route dependencies to get a database session.
    
    Example:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            # Use db here
            pass
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
