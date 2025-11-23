"""
Billing Router - API endpoints for Stripe billing integration
Webhook is defined FIRST to avoid middleware conflicts
"""

import os
import logging
from fastapi import APIRouter, Request, Depends, Body
from typing import Optional
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
import stripe

from database import get_db
from services.billing_service import BillingService

logger = logging.getLogger(__name__)

# Load Stripe configuration from environment variables
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Initialize Stripe client
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
else:
    logger.warning("STRIPE_SECRET_KEY is not set. Stripe functionality will be unavailable.")

# Create billing router
billing_router = APIRouter(prefix="/api/billing", tags=["billing"])


# WEBHOOK ENDPOINT - MUST BE DEFINED FIRST TO AVOID MIDDLEWARE CONFLICTS
@billing_router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Stripe webhook events with signature verification.
    
    This endpoint verifies the Stripe webhook signature before processing events.
    Only verified events are processed to prevent spoofing attacks.
    
    Always returns 200 OK to Stripe to prevent retries.
    
    Args:
        request: FastAPI Request object (for raw body)
        db: Database session dependency
        
    Returns:
        JSON response with 200 status code
    """
    try:
        # Load webhook secret from environment variable
        webhook_secret = STRIPE_WEBHOOK_SECRET
        if not webhook_secret:
            logger.error("STRIPE_WEBHOOK_SECRET environment variable is not set")
            # Return 200 to Stripe even if secret is missing to prevent retries
            return JSONResponse(
                status_code=200,
                content={"ok": False, "received": True, "error": "Webhook secret not configured"}
            )
        
        # Get raw request body (required for signature verification)
        payload = await request.body()
        
        # Get Stripe signature from header
        stripe_signature = request.headers.get("stripe-signature")
        if not stripe_signature:
            logger.error("Missing Stripe-Signature header")
            return JSONResponse(
                status_code=200,
                content={"ok": False, "received": True, "error": "Missing signature header"}
            )
        
        # Verify webhook signature using Stripe's construct_event method
        try:
            event = stripe.webhook.construct_event(
                payload,
                stripe_signature,
                webhook_secret
            )
        except stripe.SignatureVerificationError as e:
            # Signature verification failed - this is a fake request
            logger.error(f"Stripe webhook signature verification failed: {e}")
            # Return 200 to Stripe to prevent retries (even for invalid signatures)
            return JSONResponse(
                status_code=200,
                content={"ok": False, "received": True, "error": "Invalid webhook signature"}
            )
        except ValueError as e:
            # Invalid payload format
            logger.error(f"Invalid webhook payload: {e}")
            return JSONResponse(
                status_code=200,
                content={"ok": False, "received": True, "error": "Invalid payload format"}
            )
        
        # Initialize billing service without user repository (decoupled from auth)
        billing_service = BillingService(db)
        
        # Process the verified webhook event
        result = await billing_service.process_webhook(event)
        
        # Always return 200 to Stripe (even on processing failure) to prevent retries
        # Webhook needs special handling - always return 200 to Stripe
        success = not result.get("is_error", True)
        return JSONResponse(
            status_code=200,
            content={
                "ok": success,
                "received": True,
                "event_type": event.type
            }
        )
            
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        # Return 200 to Stripe even on error to prevent retries
        return JSONResponse(
            status_code=200,
            content={"ok": False, "received": True, "error": str(e)}
        )


@billing_router.post("/create-checkout-session")
async def create_checkout_session(
    email: Optional[str] = Body(default=None),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a Stripe Checkout session (decoupled from auth).
    Uses anonymous customer if no email provided.
    
    Args:
        email: Optional email address for Stripe customer creation
        db: Database session dependency
        
    Returns:
        JSON response with checkout session URL
    """
    from backend.utils.responses import success_response, error_response
    
    result = await BillingService(db).create_checkout_session(email)
    if result.get("is_error"):
        return error_response(result.get("error", "Unknown error"))
    return success_response(result["data"])


@billing_router.post("/portal")
async def create_billing_portal_session(
    stripe_customer_id: str = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a Stripe Billing Portal session (decoupled from auth).
    
    Args:
        stripe_customer_id: Stripe customer ID
        db: Database session dependency
        
    Returns:
        JSON response with portal session URL
    """
    from backend.utils.responses import success_response, error_response
    
    result = await BillingService(db).create_billing_portal_session(stripe_customer_id)
    if result.get("is_error"):
        return error_response(result.get("error", "Unknown error"))
    return success_response(result["data"])
