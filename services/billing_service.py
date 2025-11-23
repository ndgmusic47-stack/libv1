"""
Billing Service - Full Stripe billing integration with trial logic
"""

import os
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
import stripe

# Removed UserRepository and User imports - decoupled from auth
from config.settings import settings

logger = logging.getLogger(__name__)

# Load Stripe configuration from environment variables
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
STRIPE_PRODUCT_ID = os.getenv("STRIPE_PRODUCT_ID")

# Initialize Stripe client
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
else:
    logger.warning("STRIPE_SECRET_KEY is not set. Stripe functionality will be unavailable.")


class BillingService:
    """
    Service class for handling billing-related business logic.
    Decoupled from authentication - works with email/Stripe customer IDs directly.
    """
    
    def __init__(self, db: AsyncSession):
        """
        Initialize the billing service.
        
        Args:
            db: AsyncSession instance for database operations
        """
        self.db = db
    
    async def create_checkout_session(self, email: Optional[str] = None):
        """
        Create a Stripe Checkout session (decoupled from auth).
        Uses anonymous customer if no email provided.
        
        Args:
            email: Optional email address for Stripe customer creation
            
        Returns:
            Normalized response: {"data": url, "is_error": False} or {"error": str(e), "is_error": True}
        """
        if not STRIPE_SECRET_KEY:
            logger.error("STRIPE_SECRET_KEY is not set. Cannot create checkout session.")
            return {"error": "STRIPE_SECRET_KEY is not set. Cannot create checkout session.", "is_error": True}
        
        if not STRIPE_PRICE_ID:
            logger.error("STRIPE_PRICE_ID is not set. Cannot create checkout session.")
            return {"error": "STRIPE_PRICE_ID is not set. Cannot create checkout session.", "is_error": True}
        
        try:
            # Create anonymous Stripe customer if no email provided
            if email:
                # Create or retrieve Stripe customer by email (decoupled from auth)
                customers = stripe.Customer.list(email=email, limit=1)
                if customers.data:
                    customer_id = customers.data[0].id
                else:
                    customer = stripe.Customer.create(
                        email=email,
                        metadata={"email": email}
                    )
                    customer_id = customer.id
            else:
                # Create anonymous customer
                customer = stripe.Customer.create(
                    email="anonymous@liab.com",
                    metadata={"anonymous": "true"}
                )
                customer_id = customer.id
            
            # Get frontend URL from config
            frontend_url = settings.frontend_url or "http://localhost:5173"
            
            # Create checkout session
            checkout_session = stripe.checkout.Session.create(
                customer=customer_id,
                payment_method_types=["card"],
                line_items=[{
                    "price": STRIPE_PRICE_ID,
                    "quantity": 1,
                }],
                mode="subscription",
                success_url=f"{frontend_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{frontend_url}/billing/cancel",
                metadata={
                    "email": email
                }
            )
            
            return {"data": checkout_session.url, "is_error": False}
        except Exception as e:
            logger.error(f"Failed to create checkout session: {e}", exc_info=True)
            return {"error": str(e), "is_error": True}
    
    async def create_billing_portal_session(self, stripe_customer_id: str):
        """
        Create a Stripe Billing Portal session (decoupled from auth).
        
        Args:
            stripe_customer_id: Stripe customer ID
            
        Returns:
            Normalized response: {"data": url, "is_error": False} or {"error": str(e), "is_error": True}
        """
        if not STRIPE_SECRET_KEY:
            logger.error("STRIPE_SECRET_KEY is not set. Cannot create billing portal session.")
            return {"error": "STRIPE_SECRET_KEY is not set. Cannot create billing portal session.", "is_error": True}
        
        if not stripe_customer_id:
            logger.error("Stripe customer ID is required.")
            return {"error": "Stripe customer ID is required.", "is_error": True}
        
        try:
            # Get frontend URL from config
            frontend_url = settings.frontend_url or "http://localhost:5173"
            
            # Create billing portal session
            portal_session = stripe.billing_portal.Session.create(
                customer=stripe_customer_id,
                return_url=f"{frontend_url}/settings"
            )
            
            return {"data": portal_session.url, "is_error": False}
        except Exception as e:
            logger.error(f"Failed to create billing portal session: {e}", exc_info=True)
            return {"error": str(e), "is_error": True}
    
    async def process_webhook(self, event: stripe.Event):
        """
        Process a Stripe webhook event (decoupled from auth).
        Simply logs events without updating database users.
        
        Args:
            event: Verified Stripe Event object (from webhook signature verification)
            
        Returns:
            Normalized response: {"data": True, "is_error": False} or {"error": str(e), "is_error": True}
        """
        try:
            event_type = event.type
            logger.info(f"Processing Stripe webhook event: {event_type} (decoupled from auth)")
            
            # For now, just acknowledge receipt - webhooks work but don't update user records
            # Stripe subscription state is the source of truth
            return {"data": True, "is_error": False}
            
        except Exception as e:
            logger.error(f"Error processing webhook: {e}", exc_info=True)
            return {"error": str(e), "is_error": True}
