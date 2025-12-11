import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../utils/api';

// Optional: Web Speech synthesis handle (kept for future use if needed)
let synthesis = null;
if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
  synthesis = window.speechSynthesis;
}

// Single global audio instance for voice playback
let globalVoiceAudio = null;

export const useVoice = (sessionId = null) => {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [interimTranscript, setInterimTranscript] = useState('');
  const [recognition, setRecognition] = useState(null);
  const [lastIntent, setLastIntent] = useState(null);
  const isMutedRef = useRef(false);
  const isPausedRef = useRef(false);

  // --- SPEECH RECOGNITION SETUP ---
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) return;

    const recognitionInstance = new SpeechRecognition();
    recognitionInstance.continuous = true;
    recognitionInstance.interimResults = true;
    recognitionInstance.lang = 'en-US';

    recognitionInstance.onresult = (event) => {
      let interim = '';
      let finalText = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcriptPiece = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalText += transcriptPiece;
        } else {
          interim += transcriptPiece;
        }
      }

      setInterimTranscript(interim);
      if (finalText) {
        setTranscript((prev) => (prev + ' ' + finalText).trim());
      }
    };

    recognitionInstance.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      setIsListening(false);
    };

    recognitionInstance.onend = () => {
      setIsListening(false);
    };

    setRecognition(recognitionInstance);

    return () => {
      recognitionInstance.stop();
    };
  }, []);

  const startListening = useCallback(() => {
    if (recognition && !isListening) {
      recognition.start();
      setIsListening(true);
      setTranscript('');
      setInterimTranscript('');
    }
  }, [recognition, isListening]);

  const stopListening = useCallback(() => {
    if (recognition && isListening) {
      recognition.stop();
      setIsListening(false);
    }
  }, [recognition, isListening]);

  // --- VOICE PLAYBACK (BACKEND + HTMLAUDIO) ---
  const speak = useCallback(
    async (text, persona = null) => {
      try {
        const selectedPersona = persona || 'nova';

        const result = await api.voiceSpeak(selectedPersona, text, sessionId);

        if (!result || !result.url) {
          throw new Error('No audio URL returned from backend');
        }

        // Stop any currently playing audio
        if (globalVoiceAudio) {
          try {
            globalVoiceAudio.pause();
            globalVoiceAudio.currentTime = 0;
          } catch (e) {
            console.warn('Failed to reset previous audio instance', e);
          }
          globalVoiceAudio = null;
        }

        // Create new audio instance
        const audio = new Audio(result.url);
        audio.volume = 1.0;
        audio.muted = isMutedRef.current;

        audio.onended = () => {
          globalVoiceAudio = null;
        };

        audio.onerror = () => {
          console.error('Audio playback error');
          globalVoiceAudio = null;
        };

        globalVoiceAudio = audio;

        // Start playback
        await audio.play().catch((err) => {
          console.error('Audio play failed:', err);
          globalVoiceAudio = null;
        });

        // Resolve when audio stops or after 30s timeout
        return new Promise((resolve, reject) => {
          if (!globalVoiceAudio) {
            resolve();
            return;
          }

          const checkEnded = setInterval(() => {
            if (!globalVoiceAudio) {
              clearInterval(checkEnded);
              resolve();
              return;
            }

            if (globalVoiceAudio.ended || globalVoiceAudio.paused) {
              clearInterval(checkEnded);
              if (globalVoiceAudio.ended) {
                resolve();
              } else if (globalVoiceAudio.error) {
                reject(new Error('Audio playback error'));
              } else {
                resolve();
              }
            }
          }, 100);

          setTimeout(() => {
            clearInterval(checkEnded);
            resolve();
          }, 30000);
        });
      } catch (err) {
        console.error('Voice speak failed:', err);
        throw err;
      }
    },
    [sessionId]
  );

  const stopSpeaking = useCallback(async () => {
    try {
      await api.voiceStop(sessionId);
    } catch (err) {
      console.error('Backend voice stop failed:', err);
    }

    if (globalVoiceAudio) {
      try {
        globalVoiceAudio.pause();
        globalVoiceAudio.currentTime = 0;
      } catch (e) {
        console.warn('Failed to stop audio instance', e);
      }
      globalVoiceAudio = null;
    }
  }, [sessionId]);

  const muteSpeaking = useCallback(
    async () => {
      try {
        await api.voiceMute(sessionId);
      } catch (err) {
        console.error('Backend voice mute failed:', err);
      }

      isMutedRef.current = true;
      if (globalVoiceAudio) {
        globalVoiceAudio.muted = true;
      }
    },
    [sessionId]
  );

  const unmuteSpeaking = useCallback(() => {
    isMutedRef.current = false;
    if (globalVoiceAudio) {
      globalVoiceAudio.muted = false;
    }
  }, []);

  const pauseSpeaking = useCallback(
    async () => {
      try {
        await api.voicePause(sessionId);
      } catch (err) {
        console.error('Backend voice pause failed:', err);
      }

      if (globalVoiceAudio && !globalVoiceAudio.paused) {
        globalVoiceAudio.pause();
        isPausedRef.current = true;
      }
    },
    [sessionId]
  );

  const resumeSpeaking = useCallback(() => {
    if (globalVoiceAudio && globalVoiceAudio.paused) {
      globalVoiceAudio.play().catch((err) => {
        console.error('Failed to resume audio', err);
      });
      isPausedRef.current = false;
    }
  }, []);

  // --- INTENT HANDLING ---
  const processCommand = useCallback(
    async (command) => {
      if (!sessionId) {
        console.warn('No session ID provided for intent processing');
        return null;
      }

      try {
        const result = await api.processIntent(sessionId, command);
        setLastIntent(result);

        if (result && result.voice_response) {
          await speak(result.voice_response);
        }

        return result;
      } catch (err) {
        console.error('Failed to process intent:', err);
        try {
          await speak("Sorry, I didn't understand that command.");
        } catch (_) {
          // ignore fallback errors
        }
        return null;
      }
    },
    [sessionId, speak]
  );

  const listenForCommand = useCallback(async () => {
    if (!recognition) return null;

    return new Promise((resolve) => {
      const handleResult = async (event) => {
        for (let i = event.resultIndex; i < event.results.length; i++) {
          if (event.results[i].isFinal) {
            const command = event.results[i][0].transcript;
            recognition.stop();

            const intent = await processCommand(command);
            resolve(intent);
            return;
          }
        }
      };

      recognition.onresult = handleResult;
      recognition.start();
      setIsListening(true);
    });
  }, [recognition, processCommand]);

  return {
    isListening,
    transcript,
    interimTranscript,
    startListening,
    stopListening,
    speak,
    stopSpeaking,
    muteSpeaking,
    unmuteSpeaking,
    pauseSpeaking,
    resumeSpeaking,
    processCommand,
    listenForCommand,
    lastIntent,
    isSupported: !!recognition,
  };
};
