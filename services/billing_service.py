"""
Billing Service - Full Stripe billing integration with trial logic
"""

import os
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
import stripe

from crud.user import UserRepository
from database_models import User
from config import settings

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
    Uses dependency injection for database session and user repository.
    """
    
    def __init__(self, db: AsyncSession, user_repo: UserRepository):
        """
        Initialize the billing service.
        
        Args:
            db: AsyncSession instance for database operations
            user_repo: UserRepository instance for user operations
        """
        self.db = db
        self.user_repo = user_repo
    
    async def create_checkout_session(self, user: User) -> Optional[str]:
        """
        Create a Stripe Checkout session for a user.
        
        Args:
            user: User object to create checkout session for
            
        Returns:
            Checkout session URL if successful, None otherwise
        """
        if not STRIPE_SECRET_KEY:
            logger.error("STRIPE_SECRET_KEY is not set. Cannot create checkout session.")
            return None
        
        if not STRIPE_PRICE_ID:
            logger.error("STRIPE_PRICE_ID is not set. Cannot create checkout session.")
            return None
        
        try:
            # Get or create Stripe customer
            customer_id = user.stripe_customer_id
            if not customer_id:
                customer = stripe.Customer.create(
                    email=user.email,
                    metadata={"user_id": str(user.id)}
                )
                customer_id = customer.id
                # Update user with customer ID
                await self.user_repo.update_user(user, {"stripe_customer_id": customer_id})
                await self.db.commit()
            
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
                    "user_id": str(user.id)
                }
            )
            
            return checkout_session.url
        except Exception as e:
            logger.error(f"Failed to create checkout session: {e}", exc_info=True)
            return None
    
    async def create_billing_portal_session(self, user: User) -> Optional[str]:
        """
        Create a Stripe Billing Portal session for a user.
        
        Args:
            user: User object to create portal session for
            
        Returns:
            Portal session URL if successful, None otherwise
        """
        if not STRIPE_SECRET_KEY:
            logger.error("STRIPE_SECRET_KEY is not set. Cannot create billing portal session.")
            return None
        
        if not user.stripe_customer_id:
            logger.error(f"User {user.id} does not have a Stripe customer ID.")
            return None
        
        try:
            # Get frontend URL from config
            frontend_url = settings.frontend_url or "http://localhost:5173"
            
            # Create billing portal session
            portal_session = stripe.billing_portal.Session.create(
                customer=user.stripe_customer_id,
                return_url=f"{frontend_url}/settings"
            )
            
            return portal_session.url
        except Exception as e:
            logger.error(f"Failed to create billing portal session: {e}", exc_info=True)
            return None
    
    def _extract_user_id_from_event(self, event_type: str, event_object) -> Optional[str]:
        """
        Extract user_id from Stripe event metadata.
        
        Args:
            event_type: Type of Stripe event
            event_object: Stripe event object
            
        Returns:
            user_id as string if found, None otherwise
        """
        customer_id = getattr(event_object, "customer", None)
        customer_metadata = getattr(event_object, "metadata", None)
        
        # Extract user_id from metadata if available
        user_id_str = self._get_user_id_from_metadata(customer_metadata)
        
        # If not in subscription/checkout metadata, fetch customer from Stripe
        if not user_id_str and customer_id:
            if not STRIPE_SECRET_KEY:
                logger.warning("STRIPE_SECRET_KEY is not set. Cannot fetch customer from Stripe.")
            else:
                try:
                    customer = stripe.Customer.retrieve(customer_id)
                    customer_metadata = getattr(customer, "metadata", None)
                    user_id_str = self._get_user_id_from_metadata(customer_metadata)
                except Exception as e:
                    logger.error(f"Failed to fetch customer {customer_id} from Stripe: {e}")
        
        return user_id_str
    
    def _get_user_id_from_metadata(self, metadata) -> Optional[str]:
        """
        Extract user_id from Stripe metadata object.
        
        Args:
            metadata: Stripe metadata object (dict or object with attributes)
            
        Returns:
            user_id as string if found, None otherwise
        """
        if not metadata:
            return None
        
        if isinstance(metadata, dict):
            return metadata.get("user_id")
        else:
            return getattr(metadata, "user_id", None)
    
    async def process_webhook(self, event: stripe.Event) -> bool:
        """
        Process a Stripe webhook event.
        
        Subscription rules:
        - When checkout completed → subscription_status="active"
        - When subscription created/updated → sync stripe_subscription_id, stripe_price_id
        - When subscription canceled → subscription_status="expired"
        - When invoice.payment_failed → subscription_status="expired"
        
        Args:
            event: Verified Stripe Event object (from webhook signature verification)
            
        Returns:
            True if processing was successful, False otherwise
        """
        try:
            event_type = event.type
            event_data = event.data
            event_object = event_data.object
            
            logger.info(f"Processing Stripe webhook event: {event_type}")
            
            # Handle checkout.session.completed
            if event_type == "checkout.session.completed":
                return await self._handle_checkout_completed(event_object)
            
            # Handle subscription events
            elif event_type in ["customer.subscription.created", "customer.subscription.updated"]:
                return await self._handle_subscription_created_or_updated(event_object)
            
            # Handle subscription canceled
            elif event_type == "customer.subscription.deleted":
                return await self._handle_subscription_deleted(event_object)
            
            # Handle payment failed
            elif event_type == "invoice.payment_failed":
                return await self._handle_payment_failed(event_object)
            
            else:
                logger.info(f"Unhandled event type: {event_type}")
                return True  # Return True to acknowledge receipt
            
        except Exception as e:
            logger.error(f"Error processing webhook: {e}", exc_info=True)
            await self.db.rollback()
            return False
    
    async def _handle_checkout_completed(self, session_object) -> bool:
        """Handle checkout.session.completed event"""
        try:
            # Extract user_id from metadata
            user_id_str = self._get_user_id_from_metadata(getattr(session_object, "metadata", None))
            if not user_id_str:
                logger.error("Could not extract user_id from checkout session metadata")
                return False
            
            user_id = int(user_id_str)
            user = await self.user_repo.get_user_by_id(user_id)
            if not user:
                logger.error(f"User not found for user_id: {user_id}")
                return False
            
            # Get subscription ID from session
            subscription_id = getattr(session_object, "subscription", None)
            
            # Update user subscription status
            updates = {
                "subscription_status": "active",
                "is_paid_user": True
            }
            
            if subscription_id:
                updates["stripe_subscription_id"] = subscription_id
                # Fetch subscription to get price_id
                try:
                    subscription = stripe.Subscription.retrieve(subscription_id)
                    if subscription.items and len(subscription.items.data) > 0:
                        price_id = subscription.items.data[0].price.id
                        updates["stripe_price_id"] = price_id
                except Exception as e:
                    logger.warning(f"Failed to fetch subscription details: {e}")
            
            await self.user_repo.update_user(user, updates)
            await self.db.commit()
            logger.info(f"Updated user {user_id} to active subscription after checkout")
            return True
            
        except Exception as e:
            logger.error(f"Error handling checkout completed: {e}", exc_info=True)
            await self.db.rollback()
            return False
    
    async def _handle_subscription_created_or_updated(self, subscription_object) -> bool:
        """Handle customer.subscription.created or customer.subscription.updated events"""
        try:
            # Extract user_id from customer metadata
            customer_id = getattr(subscription_object, "customer", None)
            user_id_str = None
            
            if customer_id:
                user_id_str = self._extract_user_id_from_event("subscription.updated", subscription_object)
            
            if not user_id_str:
                logger.error("Could not extract user_id from subscription event")
                return False
            
            user_id = int(user_id_str)
            user = await self.user_repo.get_user_by_id(user_id)
            if not user:
                logger.error(f"User not found for user_id: {user_id}")
                return False
            
            # Get subscription details
            subscription_id = getattr(subscription_object, "id", None)
            subscription_status = getattr(subscription_object, "status", None)
            
            # Get price_id from subscription items
            price_id = None
            items = getattr(subscription_object, "items", None)
            if items and hasattr(items, "data") and len(items.data) > 0:
                price_id = items.data[0].price.id
            
            # Update user with subscription info
            updates = {}
            if subscription_id:
                updates["stripe_subscription_id"] = subscription_id
            if price_id:
                updates["stripe_price_id"] = price_id
            
            # Update subscription status and is_paid_user based on status
            if subscription_status:
                if subscription_status == "active":
                    updates["subscription_status"] = "active"
                    updates["is_paid_user"] = True
                elif subscription_status in ["canceled", "unpaid", "past_due", "incomplete_expired"]:
                    updates["subscription_status"] = "expired"
                    updates["is_paid_user"] = False
                else:
                    updates["subscription_status"] = subscription_status.lower()
            
            if updates:
                await self.user_repo.update_user(user, updates)
                await self.db.commit()
                logger.info(f"Updated user {user_id} subscription info: {updates}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling subscription created/updated: {e}", exc_info=True)
            await self.db.rollback()
            return False
    
    async def _handle_subscription_deleted(self, subscription_object) -> bool:
        """Handle customer.subscription.deleted event"""
        try:
            # Extract user_id from customer metadata
            customer_id = getattr(subscription_object, "customer", None)
            user_id_str = None
            
            if customer_id:
                user_id_str = self._extract_user_id_from_event("subscription.deleted", subscription_object)
            
            if not user_id_str:
                logger.error("Could not extract user_id from subscription deleted event")
                return False
            
            user_id = int(user_id_str)
            user = await self.user_repo.get_user_by_id(user_id)
            if not user:
                logger.error(f"User not found for user_id: {user_id}")
                return False
            
            # Update user subscription status to expired
            await self.user_repo.update_user(user, {
                "subscription_status": "expired",
                "is_paid_user": False
            })
            await self.db.commit()
            logger.info(f"Updated user {user_id} to expired after subscription deletion")
            return True
            
        except Exception as e:
            logger.error(f"Error handling subscription deleted: {e}", exc_info=True)
            await self.db.rollback()
            return False
    
    async def _handle_payment_failed(self, invoice_object) -> bool:
        """Handle invoice.payment_failed event"""
        try:
            # Extract user_id from customer metadata
            customer_id = getattr(invoice_object, "customer", None)
            user_id_str = None
            
            if customer_id:
                user_id_str = self._extract_user_id_from_event("invoice.payment_failed", invoice_object)
            
            if not user_id_str:
                logger.error("Could not extract user_id from invoice payment failed event")
                return False
            
            user_id = int(user_id_str)
            user = await self.user_repo.get_user_by_id(user_id)
            if not user:
                logger.error(f"User not found for user_id: {user_id}")
                return False
            
            # Update user subscription status to expired
            await self.user_repo.update_user(user, {
                "subscription_status": "expired",
                "is_paid_user": False
            })
            await self.db.commit()
            logger.info(f"Updated user {user_id} to expired after payment failed")
            return True
            
        except Exception as e:
            logger.error(f"Error handling payment failed: {e}", exc_info=True)
            await self.db.rollback()
            return False
