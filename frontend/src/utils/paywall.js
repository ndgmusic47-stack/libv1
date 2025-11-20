/**
 * Paywall helper utilities
 * Handles user-based access control and upgrade_required responses from the API
 */

export function checkUserAccess(user) {
  if (!user) return { allowed: false, reason: "Please log in to continue." };

  if (user.subscription_status === "active") {
    return { allowed: true, reason: null };
  }

  if (user.trial_active) {
    return { allowed: true, reason: null };
  }

  return {
    allowed: false,
    reason: "Your trial has ended. Subscribe to unlock this feature."
  };
}

export function handlePaywall(response, openUpgradeModal) {
  if (response && response.error === "upgrade_required") {
    openUpgradeModal(response.feature);
    return false;
  }
  return true;
}

