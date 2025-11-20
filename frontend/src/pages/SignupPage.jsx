import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth } from '../context/AuthContext';
import GoogleSignInButton from '../components/GoogleSignInButton';

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
    <div className="min-h-screen bg-studio-indigo flex items-center justify-center p-4">
      <motion.div
        className="bg-studio-gray border border-studio-white/20 rounded-lg max-w-md w-full p-6"
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: 'spring', stiffness: 300, damping: 25 }}
      >
        <h3 className="text-lg text-studio-gold font-montserrat mb-4">
          ✨ Sign Up
        </h3>

        <div className="mb-4 pb-4 border-b border-studio-white/20">
          <button
            type="button"
            onClick={() => navigate('/login')}
            disabled={loading}
            className="text-base text-studio-gold hover:text-studio-gold/80 font-montserrat font-medium transition-colors disabled:opacity-50 underline"
          >
            Already have an account? Sign in
          </button>
        </div>

        <div className="mb-4">
          <h2 className="text-xl text-studio-white font-montserrat font-semibold mb-2">
            Create Music Faster with AI-Powered Automation
          </h2>
          <p className="text-base text-studio-gold font-poppins font-medium">
            Start your 3-Day Free Trial — No Credit Card Required.
          </p>
        </div>
        
        <div className="flex flex-col gap-4 mb-4">
          <GoogleSignInButton />
        </div>

        <div className="relative my-4">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-studio-white/20"></div>
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-2 bg-studio-gray text-studio-white/60 font-poppins">OR</span>
          </div>
        </div>
        
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
              'Start Free Trial'
            )}
          </motion.button>
        </form>
      </motion.div>
    </div>
  );
}

