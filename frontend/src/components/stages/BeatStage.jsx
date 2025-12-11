import { useState } from 'react';
import { motion } from 'framer-motion';
import { api } from '../../utils/api';
import StageWrapper from './StageWrapper';

export default function BeatStage({ openUpgradeModal, sessionId, sessionData, updateSessionData, voice, onClose, onNext, onBack, completeStage }) {

  const [mood, setMood] = useState(sessionData.mood || 'energetic');
  const [promptText, setPromptText] = useState('');
  const [loading, setLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [beatMetadata, setBeatMetadata] = useState(null);

  const handleGenerateClick = () => {
    if (!promptText.trim()) {
      setError('Please describe the beat you want');
      return;
    }
    setShowModal(true);
  };

  const handleModalCancel = () => {
    setShowModal(false);
  };

  const handleCreate = async () => {
    setShowModal(false);
    setIsGenerating(true);
    setLoading(true);
    setError(null);
    
    try {
      voice.speak(`Creating a ${mood} beat for you...`);
      
      // Call beat creation API with promptText, mood, and genre
      const result = await api.createBeat(promptText, mood, sessionData.genre || 'hip hop', sessionId);
      
      // Extract metadata from result if available
      const metadata = result.metadata || null;
      if (metadata) {
        setBeatMetadata(metadata);
      }
      
      // Sync beat metadata into project memory correctly
      updateSessionData({ 
        mood: mood,
        beatMetadata: metadata,   // includes bpm, key, duration
        beatFile: result.beat_url || result.url,  // already returned
      });
      
      // For now, do NOT call syncProject here.
      // We rely on the direct API response for beatFile in this stage.
      
      // Mark beat stage as complete
      if (completeStage) {
        completeStage('beat');
      }
      
      voice.speak('Your beat is ready! Check it out.');
    } catch (err) {
      setError(err.message);
      voice.speak('Sorry, there was an error creating the beat.');
    } finally {
      setLoading(false);
      setIsGenerating(false);
    }
  };

  const handleVoiceCommand = (transcript) => {
    const lowerTranscript = transcript.toLowerCase();
    
    if (lowerTranscript.includes('create') || lowerTranscript.includes('make')) {
      const moods = ['energetic', 'chill', 'dark', 'happy', 'sad', 'aggressive'];
      const foundMood = moods.find(m => lowerTranscript.includes(m));
      
      if (foundMood) {
        setMood(foundMood);
      }
      
      // Use transcript as prompt (remove "create" and "make" keywords)
      const cleanTranscript = transcript.replace(/\b(create|make)\b/gi, '').trim();
      if (cleanTranscript.length > 0) {
        setPromptText(cleanTranscript);
        // Do NOT auto-generate - just fill fields and speak back
        voice.speak('Beat description ready. Tap Generate when you\'re ready.');
      }
    }
  };

  return (
    <StageWrapper 
      title="Create Beat" 
      icon="🎵" 
      onClose={onClose}
      onNext={onNext}
      onBack={onBack}
      voice={voice}
      onVoiceCommand={handleVoiceCommand}
    >
      <div className="w-full h-full flex flex-col items-center justify-start p-6 md:p-10">
        <div className="icon-wrapper text-6xl mb-4">
          🎵
        </div>

        <div className="w-full max-w-md space-y-6">
          <div>
            <label className="block text-xs text-studio-white/60 font-montserrat mb-2">
              Describe the beat you want
            </label>
            <input
              type="text"
              value={promptText}
              onChange={(e) => setPromptText(e.target.value)}
              className="w-full px-4 py-3 bg-studio-gray/50 border border-studio-white/20 rounded-lg
                       text-studio-white font-poppins focus:outline-none focus:border-studio-red
                       transition-colors"
              placeholder="e.g., energetic trap beat with heavy bass..."
            />
          </div>

          <div>
            <label className="block text-xs text-studio-white/60 font-montserrat mb-2">
              Mood
            </label>
            <input
              type="text"
              value={mood}
              onChange={(e) => setMood(e.target.value)}
              className="w-full px-4 py-3 bg-studio-gray/50 border border-studio-white/20 rounded-lg
                       text-studio-white font-poppins focus:outline-none focus:border-studio-red
                       transition-colors"
              placeholder="energetic, chill, dark..."
            />
          </div>

          <motion.button
            onClick={handleGenerateClick}
            disabled={loading || isGenerating}
            className="w-full py-4 bg-studio-red hover:bg-studio-red/80 disabled:bg-studio-gray
                     text-studio-white font-montserrat font-semibold rounded-lg
                     transition-all duration-300"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            {loading ? 'Creating...' : 'Generate Beat'}
          </motion.button>

          {error && (
            <p className="text-red-400 text-sm text-center">{error}</p>
          )}

          {sessionData.beatFile && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="p-4 bg-studio-gray/30 rounded-lg border border-studio-white/10"
            >
              <p className="text-sm text-studio-white/90 mb-3 font-montserrat">Beat Ready</p>
              {beatMetadata && (
                <div className="text-sm text-studio-white/70 mb-3 font-poppins space-y-1">
                  {beatMetadata.duration && <div>• Length: {beatMetadata.duration}s</div>}
                  {beatMetadata.bpm && <div>• BPM: {beatMetadata.bpm}</div>}
                  {beatMetadata.key && <div>• Key: {beatMetadata.key}</div>}
                </div>
              )}
              <audio
                src={sessionData.beatFile}
                controls
                style={{ width: "100%", marginTop: "0.5rem" }}
              >
                Your browser does not support the audio element.
              </audio>
              <div className="flex gap-2 mt-3">
                <motion.button
                  onClick={async () => {
                    try {
                      await api.advanceStage(sessionId);
                      if (voice) {
                        try {
                          voice.speak('Beat selected. Moving to the next step.');
                        } catch (err) {
                          console.warn('Voice speak failed on Use Beat:', err);
                        }
                      }
                    } catch (err) {
                      console.error('Use Beat advanceStage error:', err);
                    }

                    if (onNext) {
                      onNext();
                    }
                  }}
                  className="flex-1 py-2 bg-studio-red/80 hover:bg-studio-red text-studio-white font-poppins text-sm rounded-lg transition-colors"
                >
                  Use Beat
                </motion.button>
                <motion.button
                  onClick={() => {
                    setPromptText('');
                    setBeatMetadata(null);
                    updateSessionData({ beatFile: null });
                  }}
                  className="flex-1 py-2 bg-studio-gray/50 hover:bg-studio-gray/70 text-studio-white font-poppins text-sm rounded-lg transition-colors"
                >
                  Clear Beat
                </motion.button>
              </div>
            </motion.div>
          )}
        </div>

        {/* Credit Warning Modal */}
        {showModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="modal-container bg-studio-gray border border-studio-white/20 rounded-lg max-w-md w-full mx-4">
              <h3 className="text-lg text-studio-gold font-montserrat mb-0">🎵 Generate a Beat?</h3>
              <p className="text-sm text-slate-200 font-poppins mb-0">
                This will create a new AI beat. It may take up to a few minutes.
              </p>
              <div className="flex gap-3">
                <motion.button
                  onClick={handleCreate}
                  disabled={isGenerating}
                  className="flex-1 py-2 bg-studio-red hover:bg-studio-red/80 disabled:bg-studio-gray
                           text-studio-white font-montserrat font-semibold rounded-lg transition-colors"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  Generate
                </motion.button>
                <motion.button
                  onClick={handleModalCancel}
                  disabled={isGenerating}
                  className="flex-1 py-2 bg-studio-gray/50 hover:bg-studio-gray/70 disabled:bg-studio-gray
                           text-studio-white font-montserrat font-semibold rounded-lg transition-colors"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  Cancel
                </motion.button>
              </div>
            </div>
          </div>
        )}

        <p className="text-xs text-studio-white/60 font-poppins text-center max-w-md">
          Try saying: "Create an energetic beat" or "Make a chill vibe"
        </p>
      </div>
    </StageWrapper>
  );
}
