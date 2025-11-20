import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { api } from '../utils/api';

export default function PricingPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const handleUpgrade = async () => {
    if (!user) {
      navigate('/login');
      return;
    }

    try {
      const res = await api.createCheckoutSession(user.user_id);
      if (res && res.url) {
        window.location.href = res.url;
      } else {
        console.error('No checkout URL returned');
      }
    } catch (err) {
      console.error('Failed to create checkout session:', err);
    }
  };

  return (
    <div className="min-h-screen bg-studio-dark flex items-center justify-center p-4">
      <motion.div
        className="bg-studio-gray border border-studio-white/20 rounded-lg max-w-2xl w-full p-8"
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: 'spring', stiffness: 300, damping: 25 }}
      >
        <h2 className="text-3xl font-montserrat text-studio-gold mb-6 text-center">
          Upgrade to NP22 Pro
        </h2>

        <div className="mb-6">
          <p className="text-studio-white/80 font-poppins mb-4">
            Unlock all premium features:
          </p>
          <ul className="space-y-3">
            <li className="flex items-center text-studio-white/90 font-poppins">
              <span className="text-studio-gold mr-3 text-xl">✓</span>
              Unlimited Projects
            </li>
            <li className="flex items-center text-studio-white/90 font-poppins">
              <span className="text-studio-gold mr-3 text-xl">✓</span>
              Unlimited Releases
            </li>
            <li className="flex items-center text-studio-white/90 font-poppins">
              <span className="text-studio-gold mr-3 text-xl">✓</span>
              Faster Mix Engine (future)
            </li>
            <li className="flex items-center text-studio-white/90 font-poppins">
              <span className="text-studio-gold mr-3 text-xl">✓</span>
              Priority Support
            </li>
          </ul>
        </div>

        <div className="flex gap-3">
          <motion.button
            onClick={handleUpgrade}
            className="flex-1 py-3 bg-studio-red hover:bg-studio-red/80
                     text-studio-white font-montserrat font-semibold rounded-lg transition-colors"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            Upgrade Now
          </motion.button>
          
          <motion.button
            type="button"
            onClick={() => navigate('/app')}
            className="flex-1 py-3 bg-studio-gray/50 hover:bg-studio-gray/70
                     text-studio-white font-montserrat font-semibold rounded-lg transition-colors"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            Back to App
          </motion.button>
        </div>
      </motion.div>
    </div>
  );
}

