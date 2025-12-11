import { useEffect } from 'react';
import { motion } from 'framer-motion';

export default function StageWrapper({ title, icon, children, onClose, onNext, onBack, voice, onVoiceCommand }) {
  useEffect(() => {
    if (voice && onVoiceCommand) {
      const checkTranscript = setInterval(() => {
        if (voice.transcript) {
          onVoiceCommand(voice.transcript);
        }
      }, 1000);

      return () => clearInterval(checkTranscript);
    }
  }, [voice, onVoiceCommand]);

  return (
    <div className="stage-wrapper">
      {/* Header with Title and Close Button */}
      <div className="stage-header">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="stage-header-title"
        >
          <span className="icon-wrapper text-3xl">{icon}</span>
          <h2 className="text-lg text-studio-gold font-bold font-montserrat">
            {title}
          </h2>
        </motion.div>

        <motion.button
          onClick={onClose}
          className="stage-close-button"
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.9 }}
        >
          <span className="text-lg">✕</span>
        </motion.button>
      </div>

      {/* Content */}
      <div className="stage-content flex flex-col items-center w-full h-full overflow-y-auto pb-8">
        {children}
      </div>

      {/* Back and Next Buttons */}
      {(onBack || onNext) && (
        <div className="stage-footer">
          {onBack && (
            <motion.button
              onClick={onBack}
              className="stage-next-button"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              ← Back
            </motion.button>
          )}
          {onNext && (
            <motion.button
              onClick={onNext}
              className="stage-next-button"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              style={{ marginLeft: onBack ? '1rem' : 0 }}
            >
              Next →
            </motion.button>
          )}
        </div>
      )}
    </div>
  );
}
