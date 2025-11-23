import { useState, useEffect } from 'react';
import { startMix, getMixStatus, getMixPreview } from "../../utils/api";
import { useProject } from "../../context/ProjectContext";
import StageWrapper from './StageWrapper';
import { TransportBar } from '../Mix/TransportBar';
import { WaveformCanvas } from '../Mix/WaveformCanvas';
import { TimelineCursor } from '../Mix/TimelineCursor';
import { useTransport } from '../../hooks/useTransport';
import { useMultiTrackWaveform } from '../../hooks/useMultiTrackWaveform';
import { useTimelineZoomPan } from '../../hooks/useTimelineZoomPan';
import PreviewPlayer from '../PreviewPlayer';

export default function MixStage({ openUpgradeModal, sessionId, sessionData, voice, onClose, onNext, completeStage }) {
  const allowed = true; // No auth - always allowed

  const projectId = sessionId;
  const { projectData, updateProject } = useProject();

  const [jobId, setJobId] = useState(null);
  const [isMixing, setIsMixing] = useState(false);
  const [mixProgress, setMixProgress] = useState(0);
  const [error, setError] = useState(null);
  
  const { playheadRatio } = useTransport(sessionId);
  const tracks = useMultiTrackWaveform(sessionId);
  
  const {
    zoom,
    offset,
    zoomIn,
    zoomOut,
    panLeft,
    panRight,
  } = useTimelineZoomPan();
  
  // Toggle states for effects
  const [applyEq, setApplyEq] = useState(false);
  const [applyCompression, setApplyCompression] = useState(false);
  const [applyLimiter, setApplyLimiter] = useState(false);
  const [applySaturation, setApplySaturation] = useState(false);

  // On mount: hydrate from existing mix
  useEffect(() => {
    if (!projectData) return;

    // Mark MIX stage complete only if projectData.mix?.completed === true
    if (projectData.mix?.completed === true && completeStage) {
      setIsMixing(false);
      // Load the preview automatically if final_output exists
      if (projectData.mix.final_output) {
        completeStage("mix", projectData.mix.final_output);
      }
    }
  }, [projectData, completeStage]);

  // Job polling loop
  useEffect(() => {
    if (!jobId) return;

    let interval = setInterval(async () => {
      try {
        const status = await getMixStatus(projectId, jobId);

        // Update progress if provided by backend
        if (status.progress) {
          setMixProgress(status.progress);
        }

        if (status.state === "complete") {
          clearInterval(interval);

          // fetch preview
          const preview = await getMixPreview(projectId);

          // update project memory
          updateProject({
            ...projectData,
            mix: {
              mix_url: preview.mix_url,
              final_output: preview.mix_url,
              completed: true
            }
          });

          setIsMixing(false);
          setJobId(null);

          // Complete stage
          if (completeStage) {
            completeStage("mix", preview.mix_url);
          }
        }
      } catch (err) {
        console.error("Polling error:", err);
        setError(`Mix status check failed: ${err.message || "Unknown error"}`);
        clearInterval(interval);
        setIsMixing(false);
        setJobId(null);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [jobId, projectId, projectData, updateProject, completeStage]);

  const handleMix = async () => {
    if (!allowed) {
      openUpgradeModal();
      return;
    }

    if (!sessionData?.vocalFile || !sessionData?.beatFile) {
      setError("Missing vocal or beat. Please complete Upload and Beat stages.");
      return;
    }

    setIsMixing(true);
    setMixProgress(0);
    setError(null);

    try {
      const res = await startMix(projectId, {});
      setJobId(res.job_id);
    } catch (err) {
      console.error("Mix start failed:", err);
      setError(`Mix failed: ${err.message || "Unknown error"}`);
      setIsMixing(false);
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
            className={`mix-btn w-full transition-all duration-200 ${
              isMixing ? "opacity-70 cursor-not-allowed" : ""
            }`}
            disabled={isMixing || !sessionData?.vocalFile || !sessionData?.beatFile}
            onClick={handleMix}
          >
            {isMixing
              ? (mixProgress > 0
                  ? `Processing… ${mixProgress}%`
                  : "Mixing…")
              : "Mix Now"
            }
          </button>

          {/* Transport Bar */}
          <TransportBar jobId={sessionId} />

          {/* Zoom/Pan Controls */}
          <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
            <button onClick={zoomOut}>-</button>
            <span>Zoom x{zoom}</span>
            <button onClick={zoomIn}>+</button>

            <button onClick={() => panLeft()}>◀</button>
            <button onClick={() => panRight(tracks.master.length)}>▶</button>
          </div>

          {/* Waveform Timeline */}
          {tracks.master.length === 0 && (
            <div style={{ color: "#888", marginBottom: 10 }}>
              Loading waveform…
            </div>
          )}
          <div style={{ position: "relative", width: "100%", height: 200 }}>
            <WaveformCanvas tracks={tracks} zoom={zoom} offset={offset} />
            <TimelineCursor
              playheadRatio={playheadRatio}
              zoom={zoom}
              offset={offset}
              waveformLength={tracks.master.length}
            />
          </div>

          {/* Audio Player */}
          <div className="mt-4 w-full">
            <PreviewPlayer />
          </div>
        </div>
      </div>
    </StageWrapper>
  );
}
