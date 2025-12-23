import { useState } from 'react';
import { motion } from 'framer-motion';
import { api } from '../../utils/api';
import StageWrapper from './StageWrapper';

export default function BeatStage({ openUpgradeModal, sessionId, sessionData, updateSessionData, onClose, onNext, onBack, completeStage }) {

  const [mood, setMood] = useState(sessionData.mood || 'energetic');
  const [promptText, setPromptText] = useState('');
  const [loading, setLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [beatMetadata, setBeatMetadata] = useState(null);
  const [statusMessage, setStatusMessage] = useState(null);

  // Poll helper for beat status
  const pollBeatStatus = async (jobId, { intervalMs = 2000, timeoutMs = 720000 } = {}) => {
    const startTime = Date.now();
    
    while (true) {
      const elapsed = Date.now() - startTime;
      if (elapsed >= timeoutMs) {
        throw new Error(`Beat generation is taking longer than expected. Beatoven is still composing. Please try again in a moment.`);
      }
      
      const status = await api.getBeatStatus(jobId);
      
      if (status.status === "ready" && status.beat_url) {
        return status;
      }
      
      if (status.status === "error") {
        throw new Error(status.error || status.message || "Beat generation failed");
      }
      
      await new Promise(r => setTimeout(r, intervalMs));
    }
  };

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
    setStatusMessage(null);
    
    try {
      // Call beat creation API with promptText, mood, and genre
      const result = await api.createBeat(promptText, mood, sessionData.genre || 'hip hop', sessionId);
      
      let finalResult = result;
      
      // If status is ready and beat_url exists, use it directly
      if (result.status === "ready" && result.beat_url) {
        // Beat is ready immediately
      } else if (result.status === "processing" && result.job_id) {
        // Poll until ready
        setStatusMessage("Generating beat…");
        updateSessionData({ beatJobId: result.job_id });
        finalResult = await pollBeatStatus(result.job_id);
      } else {
        throw new Error("Beat generation did not return a job id.");
      }
      
      // Ensure we have a valid beat_url before proceeding
      if (!finalResult.beat_url) {
        throw new Error("Beat generation completed but no beat URL was returned.");
      }
      
      // Extract metadata from result if available
      const metadata = finalResult.metadata || result.metadata || null;
      if (metadata) {
        setBeatMetadata(metadata);
      }
      
      // Sync beat metadata into project memory correctly
      updateSessionData({ 
        mood: mood,
        beatMetadata: metadata,   // includes bpm, key, duration
        beatFile: finalResult.beat_url,
      });
      
      // Mark beat stage as complete only after beatFile is set
      if (completeStage) {
        completeStage('beat');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setIsGenerating(false);
      setStatusMessage(null);
    }
  };


  return (
    <StageWrapper 
      title="Create Beat" 
      icon="🎵" 
      onClose={onClose}
      onNext={onNext}
      onBack={onBack}
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

          {statusMessage && (
            <p className="text-studio-white/70 text-sm text-center">{statusMessage}</p>
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

      </div>
    </StageWrapper>
  );
}
