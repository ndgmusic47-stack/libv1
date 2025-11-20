"""
Billing Service - Business logic for Stripe webhook handling
"""

import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
import stripe

from crud.user import UserRepository
from database_models import User
from config import settings

logger = logging.getLogger(__name__)

# Initialize Stripe with runtime check (for fetching customer metadata)
if settings.stripe_secret_key:
    stripe.api_key = settings.stripe_secret_key
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
            if not settings.stripe_secret_key:
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
    
    def _determine_subscription_status(self, event_type: str, event_object) -> str:
        """
        Determine subscription status from Stripe event.
        
        Args:
            event_type: Type of Stripe event
            event_object: Stripe event object
            
        Returns:
            Subscription status as lowercase string
        """
        if event_type == "checkout.session.completed":
            return "active"
        elif event_type == "customer.subscription.deleted":
            return "canceled"
        else:
            # For subscription.created or subscription.updated
            status = getattr(event_object, "status", "")
            return status.lower() if status else ""
    
    async def _update_user_subscription(self, user_id: int, subscription_status: str) -> bool:
        """
        Update user subscription status in database.
        
        Args:
            user_id: User ID to update
            subscription_status: Subscription status from Stripe
            
        Returns:
            True if update was successful, False otherwise
        """
        # Retrieve user from database
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            logger.error(f"User not found for user_id: {user_id}")
            return False
        
        # Update user based on subscription status
        if subscription_status == "active":
            await self.user_repo.update_user(user, {"is_paid_user": True})
            await self.db.commit()
            logger.info(f"Updated user {user_id} to paid status (active subscription)")
        elif subscription_status in ["canceled", "unpaid", "past_due", "incomplete_expired"]:
            await self.user_repo.update_user(user, {"is_paid_user": False})
            await self.db.commit()
            logger.info(f"Updated user {user_id} to free status (subscription: {subscription_status})")
        else:
            logger.warning(f"Unhandled subscription status: {subscription_status} for user {user_id}")
            return False
        
        return True
    
    async def handle_subscription_update(self, event: stripe.Event) -> bool:
        """
        Handle Stripe subscription update webhook.
        
        This method processes verified Stripe webhook events to update user subscription status.
        It extracts the user_id from Stripe Customer metadata and updates the user's
        is_paid_user status based on the subscription status.
        
        Args:
            event: Verified Stripe Event object (from webhook signature verification)
            
        Returns:
            True if processing was successful, False otherwise
        """
        try:
            event_type = event.type
            event_data = event.data
            event_object = event_data.object
            
            # Handle subscription-related events
            if event_type not in [
                "customer.subscription.created",
                "customer.subscription.updated",
                "customer.subscription.deleted",
                "checkout.session.completed"
            ]:
                logger.info(f"Unhandled event type: {event_type}")
                return True
            
            # Extract user_id from event
            user_id_str = self._extract_user_id_from_event(event_type, event_object)
            if not user_id_str:
                customer_id = getattr(event_object, "customer", None)
                logger.error(f"Could not extract user_id from Stripe payload for customer {customer_id}")
                return False
            
            # Convert user_id to integer
            try:
                user_id = int(user_id_str)
            except (ValueError, TypeError):
                logger.error(f"Invalid user_id format: {user_id_str}")
                return False
            
            # Determine subscription status
            subscription_status = self._determine_subscription_status(event_type, event_object)
            
            # Update user subscription
            return await self._update_user_subscription(user_id, subscription_status)
            
        except Exception as e:
            logger.error(f"Error processing subscription update: {e}", exc_info=True)
            await self.db.rollback()
            return False

