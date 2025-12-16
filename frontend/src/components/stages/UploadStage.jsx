import { useState, useCallback, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { api, normalizeMediaUrl } from '../../utils/api';
import StageWrapper from './StageWrapper';

export default function UploadStage({ openUpgradeModal, sessionId, sessionData, updateSessionData, onClose, onNext, onBack, completeStage }) {
  const allowed = true; // No auth - always allowed

  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [generationStatus, setGenerationStatus] = useState(null);
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const recordedChunksRef = useRef([]);

  // V20: Frontend audio validation
  const validateAudioFile = (file) => {
    // Check file size (50MB limit)
    const maxSize = 50 * 1024 * 1024; // 50MB in bytes
    if (file.size > maxSize) {
      return { valid: false, error: 'File size exceeds 50MB limit' };
    }

    // Check file extension (supported formats: .wav, .mp3, .aiff, .webm, .ogg)
    const allowedExtensions = ['.wav', '.mp3', '.aiff', '.webm', '.ogg'];
    const fileName = file.name.toLowerCase();
    const hasValidExtension = allowedExtensions.some(ext => fileName.endsWith(ext));
    
    if (!hasValidExtension) {
      return { valid: false, error: 'Unsupported format. Please use .wav, .mp3, .aiff, .webm, or .ogg' };
    }

    return { valid: true };
  };

  // Cleanup on unmount to ensure mic is released
  useEffect(() => {
    return () => {
      try {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
          mediaRecorderRef.current.stop();
        }
      } catch (e) {
        // Ignore errors during cleanup
      }
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((track) => track.stop());
        mediaStreamRef.current = null;
      }
    };
  }, []);

  const handleDrop = useCallback(async (e) => {
    e.preventDefault();
    setDragging(false);
    
    try {
      const files = Array.from(e.dataTransfer.files);
      const audioFile = files.find(f => f.type.startsWith('audio/') || f.name.match(/\.(wav|mp3|aiff|webm|ogg)$/i));
      
      if (audioFile) {
        // V20: Validate before upload
        const validation = validateAudioFile(audioFile);
        if (!validation.valid) {
          setError(validation.error);
          return;
        }
        await uploadFile(audioFile);
      } else {
        setError('Please drop an audio file (.wav, .mp3, .aiff, .webm, .ogg)');
      }
    } catch (err) {
      setError(err.message || 'An error occurred');
    }
  }, [sessionId]);

  const uploadFile = async (file) => {
    if (!allowed) {
      openUpgradeModal();
      return;
    }

    setUploading(true);
    setError(null);
    
    try {
      // V20: Frontend validation before upload
      const validation = validateAudioFile(file);
      if (!validation.valid) {
        setError(validation.error);
        setUploading(false);
        return;
      }
      
      // Upload recording
      const result = await api.uploadRecording(file, sessionId);
      
      // MVP PATCH: Extract file URL from 'file_path' returned by the FastAPI endpoint
      const fileUrl = normalizeMediaUrl(result.file_path);
      
      // V20: Update sessionData with vocal file
      updateSessionData({
        vocalFile: fileUrl,
        vocalUploaded: true
      });
      
      // V20: Auto-complete upload stage
      if (completeStage) {
        completeStage('upload');
      }
    } catch (err) {
      setError(err.message || 'Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      // V20: Validate before upload
      const validation = validateAudioFile(file);
      if (!validation.valid) {
        setError(validation.error);
        return;
      }
      uploadFile(file);
    }
  };

  const startRecording = async () => {
    if (!allowed) {
      openUpgradeModal();
      return;
    }

    if (isRecording) return;

    if (typeof navigator === 'undefined' || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError('Recording is not supported in this browser.');
      return;
    }

    if (typeof MediaRecorder === 'undefined') {
      setError('Recording is not supported in this browser.');
      return;
    }

    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      const preferredTypes = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/ogg',
      ];

      let options = {};
      let selectedType = null;

      if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported) {
        for (const type of preferredTypes) {
          if (MediaRecorder.isTypeSupported(type)) {
            options.mimeType = type;
            selectedType = type;
            break;
          }
        }
      }

      let recorder;
      try {
        recorder = new MediaRecorder(stream, options);
      } catch (err) {
        recorder = new MediaRecorder(stream);
        selectedType = recorder.mimeType || selectedType;
      }

      recordedChunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          recordedChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        try {
          const mimeType = selectedType || recorder.mimeType || 'audio/webm';
          const extension = mimeType.includes('ogg') ? '.ogg' : '.webm';
          const blob = new Blob(recordedChunksRef.current, { type: mimeType });
          if (blob.size === 0) {
            setError('Recording was empty. Please try again.');
          } else {
            const fileName = `vocal_recorded_${Date.now()}${extension}`;
            const file = new File([blob], fileName, { type: mimeType });
            await uploadFile(file);
          }
        } catch (err) {
          setError(err.message || 'Recording upload failed. Please try again.');
        } finally {
          if (mediaStreamRef.current) {
            mediaStreamRef.current.getTracks().forEach((track) => track.stop());
            mediaStreamRef.current = null;
          }
          setIsRecording(false);
        }
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsRecording(true);
    } catch (err) {
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((track) => track.stop());
        mediaStreamRef.current = null;
      }
      setIsRecording(false);
      setError(err.message || 'Could not start recording. Please check microphone permissions.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      try {
        mediaRecorderRef.current.stop();
      } catch (err) {
        setError(err.message || 'Failed to stop recording.');
      }
    }
  };

  // Extract lyrics text from sessionData.lyricsData
  const getLyricsText = () => {
    if (!sessionData?.lyricsData) return null;
    if (typeof sessionData.lyricsData === 'string') {
      return sessionData.lyricsData;
    }
    // Try lyrics_text property first
    if (sessionData.lyricsData.lyrics_text) {
      return sessionData.lyricsData.lyrics_text;
    }
    // If structured lyrics, try to extract text
    // For now, return null if we can't extract text easily
    return null;
  };

  const handleGenerateVocal = async () => {
    if (!allowed) {
      openUpgradeModal();
      return;
    }

    const lyricsText = getLyricsText();
    if (!lyricsText || !lyricsText.trim()) {
      setError('No lyrics available. Please generate lyrics first.');
      return;
    }

    setGenerating(true);
    setError(null);
    setGenerationStatus('Generating vocal...');

    try {
      const result = await api.generateVocal(sessionId, lyricsText);
      
      // Normalize returned file_path via normalizeMediaUrl
      const fileUrl = normalizeMediaUrl(result.file_path);
      
      // Update session data
      updateSessionData({
        songFile: fileUrl,
        vocalFile: fileUrl, // compat
        vocalUploaded: true
      });

      setGenerationStatus('Vocal generated successfully!');
      
      // Auto-complete upload stage
      if (completeStage) {
        completeStage('upload');
      }
    } catch (err) {
      setError(err.message || 'Vocal generation failed. Please try again.');
      setGenerationStatus(null);
    } finally {
      setGenerating(false);
    }
  };

  const handleGenerateSong = async () => {
    if (!allowed) {
      openUpgradeModal();
      return;
    }

    const lyricsText = getLyricsText();
    if (!lyricsText || !lyricsText.trim()) {
      setError('No lyrics available. Please generate lyrics first.');
      return;
    }

    setGenerating(true);
    setError(null);
    setGenerationStatus('Generating AI song...');

    try {
      const result = await api.generateSong(sessionId, lyricsText);
      
      // Normalize returned file_path via normalizeMediaUrl
      const fileUrl = normalizeMediaUrl(result.file_path);
      
      // Update session data
      updateSessionData({
        songFile: fileUrl,
        vocalFile: fileUrl, // compat
        vocalUploaded: true
      });

      setGenerationStatus('AI song generated successfully!');
      
      // Auto-complete upload stage
      if (completeStage) {
        completeStage('upload');
      }
    } catch (err) {
      setError(err.message || 'AI song generation failed. Please try again.');
      setGenerationStatus(null);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <StageWrapper 
      title="Upload Recording" 
      icon="🎤" 
      onClose={onClose}
      onNext={onNext}
      onBack={onBack}
    >
      <div className="stage-scroll-container">
        {!allowed && (
          <div className="upgrade-banner">
            <p className="text-center text-red-400 font-semibold">
              {message}
            </p>
          </div>
        )}
        <div className="flex flex-col items-center justify-center gap-8 p-6 md:p-10">
        <div className="icon-wrapper text-6xl mb-4">
          🎤
        </div>

        <motion.div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          className={`
            w-full max-w-2xl h-64 border-2 border-dashed rounded-lg
            flex flex-col items-center justify-center gap-4
            transition-all duration-300 cursor-pointer
            ${dragging 
              ? 'border-studio-red bg-studio-red/10' 
              : 'border-studio-white/20 hover:border-studio-white/40'
            }
            ${uploading ? 'opacity-50 pointer-events-none' : ''}
          `}
          whileHover={{ scale: 1.02 }}
        >
          <input
            type="file"
            id="file-input"
            accept="audio/*,.wav,.mp3,.aiff,.webm,.ogg"
            onChange={handleFileSelect}
            className="hidden"
          />
          <label htmlFor="file-input" className="cursor-pointer text-center">
            <p className="text-2xl mb-2">📁</p>
            <p className="text-sm text-studio-white/90 font-montserrat">
              {uploading ? 'Uploading...' : 'Drop your vocal recording here'}
            </p>
            <p className="text-xs text-studio-white/60 font-poppins mt-2">
              or click to browse (.wav, .mp3, .aiff, .webm, .ogg)
            </p>
          </label>
        </motion.div>

        {/* Recording controls */}
        <div className="w-full max-w-2xl space-y-3">
          <div className="flex flex-col sm:flex-row gap-3">
            <motion.button
              onClick={startRecording}
              disabled={uploading || generating || isRecording}
              className={`
                w-full sm:w-1/2 py-3 px-6 rounded-lg font-montserrat font-semibold
                transition-all duration-300
                ${uploading || generating || isRecording
                  ? 'bg-studio-gray text-studio-white/50 cursor-not-allowed'
                  : 'bg-studio-red hover:bg-studio-red/80 text-studio-white'
                }
              `}
              whileHover={uploading || generating || isRecording ? {} : { scale: 1.02 }}
              whileTap={uploading || generating || isRecording ? {} : { scale: 0.98 }}
            >
              {isRecording ? 'Recording...' : 'Record'}
            </motion.button>
            <motion.button
              onClick={stopRecording}
              disabled={!isRecording}
              className={`
                w-full sm:w-1/2 py-3 px-6 rounded-lg font-montserrat font-semibold
                transition-all duration-300
                ${!isRecording
                  ? 'bg-studio-gray text-studio-white/50 cursor-not-allowed'
                  : 'bg-studio-red hover:bg-studio-red/80 text-studio-white'
                }
              `}
              whileHover={!isRecording ? {} : { scale: 1.02 }}
              whileTap={!isRecording ? {} : { scale: 0.98 }}
            >
              Stop
            </motion.button>
          </div>
          {isRecording && (
            <p className="text-sm text-studio-red text-center">Recording…</p>
          )}
        </div>

        {/* Generate Vocal Buttons */}
        {sessionData?.lyricsData && (
          <div className="w-full max-w-2xl space-y-3">
            <motion.button
              onClick={handleGenerateVocal}
              disabled={generating || uploading}
              className={`
                w-full py-3 px-6 rounded-lg font-montserrat font-semibold
                transition-all duration-300
                ${generating || uploading
                  ? 'bg-studio-gray text-studio-white/50 cursor-not-allowed'
                  : 'bg-studio-red hover:bg-studio-red/80 text-studio-white'
                }
              `}
              whileHover={generating || uploading ? {} : { scale: 1.02 }}
              whileTap={generating || uploading ? {} : { scale: 0.98 }}
            >
              {generating ? generationStatus || 'Generating...' : 'Spoken TTS Preview'}
            </motion.button>
            <motion.button
              onClick={handleGenerateSong}
              disabled={generating || uploading}
              className={`
                w-full py-3 px-6 rounded-lg font-montserrat font-semibold
                transition-all duration-300
                ${generating || uploading
                  ? 'bg-studio-gray text-studio-white/50 cursor-not-allowed'
                  : 'bg-studio-red hover:bg-studio-red/80 text-studio-white'
                }
              `}
              whileHover={generating || uploading ? {} : { scale: 1.02 }}
              whileTap={generating || uploading ? {} : { scale: 0.98 }}
            >
              {generating ? generationStatus || 'Generating...' : 'Generate AI Song (Sung)'}
            </motion.button>
          </div>
        )}

        {error && (
          <p className="text-red-400 text-sm">{error}</p>
        )}

        {generationStatus && !error && (
          <p className="text-green-400 text-sm">{generationStatus}</p>
        )}

        {sessionData.vocalFile && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full max-w-2xl p-4 bg-studio-gray/30 rounded-lg border border-studio-white/10"
          >
            <p className="text-sm text-studio-white/90 mb-3 font-montserrat">✓ Vocal Uploaded</p>
            <audio
              src={sessionData.vocalFile}
              controls
              style={{ width: "100%", marginTop: "0.5rem" }}
            >
              Your browser does not support the audio element.
            </audio>
          </motion.div>
        )}

        {/* V20: Show context from previous stages (beat + lyrics) */}
        {sessionData.beatFile && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full max-w-2xl p-4 bg-studio-gray/30 rounded-lg border border-studio-white/10"
          >
            <p className="text-sm text-studio-white/90 mb-3 font-montserrat">Beat Preview</p>
            <audio controls src={sessionData.beatFile} className="w-full" />
          </motion.div>
        )}

        {sessionData.lyricsData && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full max-w-2xl p-4 bg-studio-gray/30 rounded-lg border border-studio-white/10"
          >
            <p className="text-sm text-studio-white/90 mb-3 font-montserrat">Lyrics</p>
            <pre className="text-sm text-studio-white/70 font-poppins whitespace-pre-wrap overflow-auto max-h-48">
              {typeof sessionData.lyricsData === 'string' 
                ? sessionData.lyricsData 
                : (sessionData.lyricsData.lyrics_text || JSON.stringify(sessionData.lyricsData, null, 2))}
            </pre>
          </motion.div>
        )}
        </div>
      </div>
    </StageWrapper>
  );
}
