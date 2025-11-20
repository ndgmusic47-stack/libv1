import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!loading && !user) {
      navigate('/login');
    }
  }, [user, loading, navigate]);

  if (loading) {
    return (
      <div className="fixed inset-0 bg-studio-dark flex items-center justify-center z-50">
        <div className="text-center">
          <div className="text-studio-white text-lg font-montserrat mb-2">Loading your account…</div>
          <div className="animate-spin text-studio-gold text-2xl">⏳</div>
        </div>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return children;
}

