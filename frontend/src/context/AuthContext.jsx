import { createContext, useContext, useEffect, useState } from "react";
import { api } from "../utils/api";

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // restore session on load
  useEffect(() => {
    api.authMe()
      .then(res => {
        // Handle both {user} and direct user object responses
        setUser(res.user || res);
      })
      .catch(() => {
        // No session found, user is not authenticated
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = async (email, password) => {
    await api.login(email, password);
    // After successful login, fetch user session
    const res = await api.authMe();
    setUser(res.user || res);
  };

  const signup = async (email, password) => {
    await api.signup(email, password);
    // After successful signup, fetch user session
    const res = await api.authMe();
    setUser(res.user || res);
  };

  const logout = async () => {
    try {
      await api.logout();
    } catch (err) {
      console.error("Logout error:", err);
    }
    setUser(null);
  };

  const refreshUser = async () => {
    try {
      const res = await api.refreshUser();  // request("/auth/me")
      // Handle both {user} and direct user object responses
      if (res?.user || res) {
        setUser(res.user || res);
        return res.user || res;
      }
    } catch (err) {
      console.error("Failed to refresh user:", err);
    }
    return null;
  };

  // Initial page load triggers refresh
  useEffect(() => {
    refreshUser();
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

