"""
Configuration settings for the application
"""
from pathlib import Path
from typing import Optional

# Handle backward compatibility with Pydantic v1 (BaseSettings in pydantic) and v2 (BaseSettings in pydantic-settings)
try:
    from pydantic_settings import BaseSettings
    PYDANTIC_V2 = True
except ImportError:
    # Fallback for Pydantic v1
    from pydantic import BaseSettings
    PYDANTIC_V2 = False

from pydantic import Field

MEDIA_DIR = Path("./media")

# Normalized Plan IDs (Phase 4C)
PLAN_FREE = "free"
PLAN_PRO = "pro"
PLAN_ENTERPRISE = "enterprise"


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Stripe billing configuration
    stripe_secret_key: Optional[str] = Field(default=None, alias="STRIPE_SECRET_KEY")
    stripe_publishable_key: Optional[str] = Field(default=None, alias="STRIPE_PUBLISHABLE_KEY")
    stripe_webhook_secret: Optional[str] = Field(default=None, alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_id: Optional[str] = Field(default=None, alias="STRIPE_PRICE_ID")
    stripe_product_id: Optional[str] = Field(default=None, alias="STRIPE_PRODUCT_ID")
    
    # API keys for external services
    beatoven_api_key: Optional[str] = Field(default=None, alias="BEATOVEN_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    getlate_api_key: Optional[str] = Field(default=None, alias="GETLATE_API_KEY")
    auphonic_api_key: Optional[str] = Field(default=None, alias="AUPHONIC_API_KEY")
    
    # Infrastructure configuration
    redis_url: Optional[str] = Field(default=None, alias="REDIS_URL")
    database_url: Optional[str] = Field(default="sqlite+aiosqlite:///./sql_app.db", alias="DATABASE_URL")
    
    # Social media and distribution
    buffer_token: Optional[str] = Field(default=None, alias="BUFFER_TOKEN")
    distrokid_key: Optional[str] = Field(default=None, alias="DISTROKID_KEY")
    
    # Pricing configuration
    price_pro_monthly: Optional[str] = Field(default=None, alias="PRICE_PRO_MONTHLY")
    
    # Frontend configuration
    frontend_url: Optional[str] = Field(default="http://localhost:5173", alias="FRONTEND_URL")
    
    # Render.com deployment configuration
    render: Optional[str] = Field(default=None, alias="RENDER")
    render_external_url: Optional[str] = Field(default=None, alias="RENDER_EXTERNAL_URL")
    render_service_name: Optional[str] = Field(default=None, alias="RENDER_SERVICE_NAME")
    
    # Environment configuration
    env: Optional[str] = Field(default=None, alias="ENV")
    
    # RVC Gradio configuration
    rvc_gradio_url: Optional[str] = Field(
        default="https://9zbdd24ix0hgj4-7897.proxy.runpod.net",
        alias="RVC_GRADIO_URL"
    )
    
    # Configuration class for Pydantic v1 (also works in v2 with deprecation warning)
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        populate_by_name = True  # Allow both field name and alias


# Apply Pydantic v2 model_config if using v2 (after class definition)
if PYDANTIC_V2:
    Settings.model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "populate_by_name": True,
    }


# Instantiate settings object
settings = Settings()

# Determine if we're in production mode
IS_PRODUCTION = bool(settings.render) or (settings.env and settings.env.lower() == "production")

