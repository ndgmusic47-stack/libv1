import { createContext, useContext, useEffect, useState } from "react";
import { api } from "../utils/api";

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [initializing, setInitializing] = useState(true);

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
      .finally(() => {
        setLoading(false);
        setInitializing(false);
      });
  }, []);

  const login = async (email, password) => {
    const res = await api.login(email, password);
    // Handle error response format
    if (res && !res.ok && res.error) {
      throw new Error(res.error);
    }
    // Set user directly from login response
    setUser(res.user || res);
  };

  const signup = async (email, password) => {
    const res = await api.signup(email, password);
    // Handle error response format
    if (res && !res.ok && res.error) {
      throw new Error(res.error);
    }
    // Set user directly from signup response
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

  return (
    <AuthContext.Provider value={{ user, loading, initializing, login, signup, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

