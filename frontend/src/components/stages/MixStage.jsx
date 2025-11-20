import { useState, useEffect } from 'react';
import { runCleanMix } from '../../utils/api';
import StageWrapper from './StageWrapper';

export default function MixStage({ sessionId, sessionData, updateSessionData, voice, onClose, onNext, completeStage }) {
  const [mixing, setMixing] = useState(false);
  const [mixUrl, setMixUrl] = useState(null);
  const [error, setError] = useState(null);
  
  // Toggle states for effects
  const [applyEq, setApplyEq] = useState(false);
  const [applyCompression, setApplyCompression] = useState(false);
  const [applyLimiter, setApplyLimiter] = useState(false);
  const [applySaturation, setApplySaturation] = useState(false);

  useEffect(() => {
    console.log("MixStage mounted", { sessionId, sessionData, mixUrl });
  }, []);

  useEffect(() => {
    if (sessionData?.masterFile) {
      setMixUrl(sessionData.masterFile);
    }
  }, [sessionData]);

  const handleMixNow = async () => {
    if (!sessionData?.vocalFile || !sessionData?.beatFile) {
      setError("Missing vocal or beat. Please complete Upload and Beat stages.");
      return;
    }

    setMixing(true);
    setError(null);
    
    try {
      const currentSessionId = sessionId || sessionStorage.getItem("session_id");
      const result = await runCleanMix(sessionData.vocalFile, sessionData.beatFile, currentSessionId);
      
      if (result?.mix_url) {
        setMixUrl(result.mix_url);
        updateSessionData({ masterFile: result.mix_url });
        
        // Complete stage
        if (completeStage) {
          completeStage("mix", result.mix_url);
        }
      }
    } catch (err) {
      console.error("Mix failed:", err);
      setError(`Mix failed: ${err.message || "Unknown error"}`);
    } finally {
      setMixing(false);
    }
  };

  return (
    <StageWrapper 
      title="Mix & Master" 
      icon="🎛️" 
      onClose={onClose}
      onNext={onNext}
      voice={voice}
    >
      <div className="stage-scroll-container">
        <div className="flex flex-col items-center justify-center gap-8 p-6 md:p-10 max-w-2xl mx-auto">
          
          {/* Effect Toggles */}
          <div className="w-full space-y-4">
            <label className="block text-sm text-studio-white/60 font-montserrat mb-2">
              Mastering Effects
            </label>
            <div className="grid grid-cols-2 gap-4">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={applyEq}
                  onChange={(e) => setApplyEq(e.target.checked)}
                  className="w-5 h-5 rounded border-studio-white/20 bg-studio-gray/50
                           text-studio-red focus:ring-studio-red focus:ring-2"
                />
                <span className="text-studio-white font-poppins">EQ</span>
              </label>
              
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={applyCompression}
                  onChange={(e) => setApplyCompression(e.target.checked)}
                  className="w-5 h-5 rounded border-studio-white/20 bg-studio-gray/50
                           text-studio-red focus:ring-studio-red focus:ring-2"
                />
                <span className="text-studio-white font-poppins">Compression</span>
              </label>
              
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={applyLimiter}
                  onChange={(e) => setApplyLimiter(e.target.checked)}
                  className="w-5 h-5 rounded border-studio-white/20 bg-studio-gray/50
                           text-studio-red focus:ring-studio-red focus:ring-2"
                />
                <span className="text-studio-white font-poppins">Limiter</span>
              </label>
              
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={applySaturation}
                  onChange={(e) => setApplySaturation(e.target.checked)}
                  className="w-5 h-5 rounded border-studio-white/20 bg-studio-gray/50
                           text-studio-red focus:ring-studio-red focus:ring-2"
                />
                <span className="text-studio-white font-poppins">Saturation</span>
              </label>
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="w-full p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300 text-sm">
              {error}
            </div>
          )}

          {/* Mix Button */}
          <button
            className="mix-btn w-full"
            disabled={mixing || !sessionData?.vocalFile || !sessionData?.beatFile}
            onClick={handleMixNow}
          >
            {mixing ? "Mixing..." : "Mix Now"}
          </button>

          {/* Audio Player */}
          {mixUrl && (
            <div className="w-full space-y-2">
              <label className="block text-sm text-studio-white/60 font-montserrat">
                Processed Audio
              </label>
              <audio controls src={mixUrl} style={{ width: "100%" }} />
            </div>
          )}
        </div>
      </div>
    </StageWrapper>
  );
}
