export function requireAuth(user, openAuthModal) {
  if (!user) {
    openAuthModal();
    return false;
  }
  return true;
}

// Helper function to make API requests with credentials
async function request(endpoint, method = "GET", body = null) {
  const API_BASE = '/api';
  const options = {
    method,
    credentials: "include",
    headers: {}
  };
  
  if (body) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  
  const response = await fetch(`${API_BASE}${endpoint}`, options);
  const result = await response.json();
  
  if (!result.ok) {
    throw new Error(result.error || result.message || 'API request failed');
  }
  
  return result.data || result;
}

export async function refreshUser() {
  const res = await request("/auth/me", "GET");
  // Note: setUser is managed in AuthContext, so we return the user
  // The caller should update the context state
  return res?.user || res;
}

