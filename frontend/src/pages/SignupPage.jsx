import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth } from '../context/AuthContext';

export default function SignupPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { signup } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await signup(email, password);
      navigate('/app');
    } catch (err) {
      setError(err.message || 'Authentication failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-studio-dark flex items-center justify-center p-4">
      <motion.div
        className="bg-studio-gray border border-studio-white/20 rounded-lg max-w-md w-full p-6"
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: 'spring', stiffness: 300, damping: 25 }}
      >
        <h3 className="text-lg text-studio-gold font-montserrat mb-4">
          ✨ Sign Up
        </h3>
        
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={loading}
              className="w-full px-4 py-2 bg-white border border-studio-white/20 rounded-lg
                       text-black font-poppins placeholder-gray-500
                       focus:outline-none focus:border-studio-gold disabled:opacity-50"
              style={{ color: 'black', backgroundColor: 'white' }}
            />
          </div>
          
          <div>
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={loading}
              className="w-full px-4 py-2 bg-white border border-studio-white/20 rounded-lg
                       text-black font-poppins placeholder-gray-500
                       focus:outline-none focus:border-studio-gold disabled:opacity-50"
              style={{ color: 'black', backgroundColor: 'white' }}
            />
            <p className="text-xs text-studio-white/60 font-poppins mt-1">
              Password must be 12+ characters with uppercase, lowercase, number, and special character.
            </p>
          </div>

          {error && (
            <p className="text-sm text-red-400 font-poppins mb-0" style={{ color: '#ef4444' }}>
              {error}
            </p>
          )}

          <motion.button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-studio-red hover:bg-studio-red/80 disabled:bg-studio-gray
                     text-studio-white font-montserrat font-semibold rounded-lg transition-colors"
            whileHover={{ scale: loading ? 1 : 1.02 }}
            whileTap={{ scale: loading ? 1 : 0.98 }}
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="animate-spin">⏳</span>
                Signing up...
              </span>
            ) : (
              'Sign Up'
            )}
          </motion.button>
        </form>

        <div className="text-center mt-4">
          <button
            type="button"
            onClick={() => navigate('/login')}
            disabled={loading}
            className="text-sm text-studio-white/60 hover:text-studio-white font-poppins transition-colors disabled:opacity-50"
          >
            Already have an account? Sign in
          </button>
        </div>
      </motion.div>
    </div>
  );
}

