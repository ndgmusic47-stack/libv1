import { useState, useEffect } from 'react';
import React from 'react';
import { motion } from 'framer-motion';
import { api } from '../../utils/api';
import StageWrapper from './StageWrapper';

// V18.1: Structured lyric parsing helper
const parseLyricsToStructured = (lyricsText) => {
  if (!lyricsText || typeof lyricsText !== 'string') return null;
  
  const sections = {};
  const lines = lyricsText.split('\n');
  let currentSection = null;
  let currentLines = [];
  
  for (const line of lines) {
    // Detect section headers: [Hook], [Chorus], [Verse 1], [Verse], [Bridge], etc.
    const sectionMatch = line.match(/^\[(Hook|Chorus|Verse\s*\d*|Bridge|Intro|Outro|Pre-Chorus)\]/i);
    
    if (sectionMatch) {
      // Save previous section
      if (currentSection && currentLines.length > 0) {
        const sectionKey = currentSection.toLowerCase().replace(/\s+/g, '').replace(/\d+/, (m) => m);
        sections[sectionKey] = currentLines.filter(l => l.trim()).join('\n');
      }
      
      // Start new section
      currentSection = sectionMatch[1];
      currentLines = [];
    } else if (line.trim()) {
      currentLines.push(line);
    }
  }
  
  // Save last section
  if (currentSection && currentLines.length > 0) {
    const sectionKey = currentSection.toLowerCase().replace(/\s+/g, '').replace(/\d+/, (m) => m);
    sections[sectionKey] = currentLines.filter(l => l.trim()).join('\n');
  }
  
  return Object.keys(sections).length > 0 ? sections : null;
};

// V18.1: Flatten structured lyrics back to text
const flattenStructuredLyrics = (structured) => {
  if (!structured) return '';
  if (typeof structured === 'string') return structured;
  
  const sections = [];
  const order = ['hook', 'intro', 'verse', 'verse1', 'verse2', 'verse3', 'prechorus', 'chorus', 'bridge', 'outro'];
  
  for (const key of order) {
    if (structured[key]) {
      sections.push(structured[key]);
    }
  }
  
  // Add any remaining sections
  for (const key in structured) {
    if (!order.includes(key) && structured[key]) {
      sections.push(structured[key]);
    }
  }
  
  return sections.join('\n\n');
};

// V18.1: Bar rhythm approximation helper
const estimateBarRhythm = (lyricsText) => {
  if (!lyricsText || typeof lyricsText !== 'string') return null;
  
  const lines = lyricsText.split('\n').filter(l => l.trim());
  const rhythmMap = {};
  
  // Simple syllable counting (vowel heuristic)
  const countSyllables = (text) => {
    text = text.toLowerCase();
    if (text.length === 0) return 0;
    const vowels = text.match(/[aeiouy]+/g);
    const syllableCount = vowels ? vowels.length : Math.ceil(text.length / 3);
    return Math.max(1, syllableCount);
  };
  
  // Estimate bars: roughly 4 syllables per bar, but adjust for character length
  const estimateBars = (line) => {
    const chars = line.length;
    const syllables = countSyllables(line);
    // Rough approximation: 4-6 syllables per bar, 8-12 chars per bar
    const barEstimate = Math.max(1, Math.round((syllables / 4 + chars / 10) / 2));
    return barEstimate;
  };
  
  // Parse sections and estimate rhythm
  const structured = parseLyricsToStructured(lyricsText);
  
  if (structured) {
    for (const [sectionKey, sectionText] of Object.entries(structured)) {
      const sectionLines = sectionText.split('\n').filter(l => l.trim());
      rhythmMap[sectionKey] = sectionLines.map(estimateBars);
    }
  } else {
    // No sections detected, estimate per line
    rhythmMap['all'] = lines.map(estimateBars);
  }
  
  return rhythmMap;
};

export default function LyricsStage({ openUpgradeModal, sessionId, sessionData, updateSessionData, voice, onClose, onNext, onBack, completeStage }) {
  const [theme, setTheme] = useState('');
  const [loading, setLoading] = useState(false);
  const [lyrics, setLyrics] = useState(null);
  const [refineText, setRefineText] = useState('');
  // V18.1: Conversation history tracking
  const [history, setHistory] = useState([]);

  // Initialize lyrics from sessionData on mount
  useEffect(() => {
    if (sessionData && sessionData.lyricsData && !lyrics) {
      setLyrics(sessionData.lyricsData);
    }
  }, [sessionData, lyrics]);

  const handleGenerateLyrics = async () => {
    if (loading) return;

    const hasSessionBeat = !!(sessionData && sessionData.beatFile);
    const hasTheme = !!(theme && theme.trim().length > 0);

    if (!hasSessionBeat && !hasTheme) {
      voice.speak('Please provide a theme or create a beat first.');
      return;
    }

    setLoading(true);

    try {
      let result;

      if (hasSessionBeat) {
        voice.speak('Generating lyrics from your session beat...');
        
        // Fetch the beat blob
        const response = await fetch(sessionData.beatFile);
        const blob = await response.blob();

        const formData = new FormData();
        formData.append("file", blob, "session-beat.wav");

        result = await api.generateLyricsFromBeat(formData, sessionId);
        voice.speak('Here are your lyrics based on the session beat.');
      } else {
        voice.speak(`Writing lyrics about ${theme}...`);
        
        result = await api.generateFreeLyrics(theme);
        voice.speak('Here are your free lyrics.');
      }

      setLyrics(result.lyrics);
      updateSessionData({ lyricsData: result.lyrics });
      if (completeStage) {
        completeStage('lyrics');
      }
    } catch (err) {
      console.error('LyricsStage error:', err);
      voice.speak('Sorry, couldn\'t generate lyrics right now.');
    } finally {
      setLoading(false);
    }
  };

  // Convert lyrics to text format for API
  const lyricsAsText = () => {
    if (!lyrics) return '';
    if (typeof lyrics === 'string') return lyrics;
    // Convert structured object to text
    return flattenStructuredLyrics(lyrics);
  };

  const handleRefineLyrics = async () => {
    if (!refineText) return;

    setLoading(true);
    try {
      const currentLyricsText = lyricsAsText();
      
      // V18.1: Get structured lyrics and rhythm metadata
      const structuredLyrics = parseLyricsToStructured(currentLyricsText);
      const rhythmMap = estimateBarRhythm(currentLyricsText);
      
      // V18.1: Get last 3 history entries
      const historyToSend = history.slice(-3);
      
      // V18.1: Add current interaction to history (before API call)
      const newHistoryEntry = {
        previousLyrics: currentLyricsText,
        instruction: refineText,
        bpm: sessionData.bpm || null
      };
      
      const result = await api.refineLyrics(
        currentLyricsText, 
        refineText, 
        sessionData.bpm,
        historyToSend,
        structuredLyrics,
        rhythmMap
      );
      
      // V18.1: Update history after successful refinement
      setHistory(prev => [...prev, newHistoryEntry].slice(-3));
      
      setLyrics(result.lyrics);
      updateSessionData({ lyricsData: result.lyrics });
      setRefineText('');
      voice.speak("Here are your refined lyrics.");
    } catch (err) {
      console.error('LyricsStage error:', err);
      voice.speak("Could not refine lyrics right now.");
    } finally {
      setLoading(false);
    }
  };

  // Removed auto-scroll effect - lyrics display statically without auto-reading

  return (
    <StageWrapper 
      title="Write Lyrics" 
      icon="📝" 
      onClose={onClose}
      onNext={onNext}
      onBack={onBack}
      voice={voice}
    >
      <div className="stage-scroll-container">
        {!lyrics ? (
          <div className="flex flex-col items-center justify-center gap-8 p-6 md:p-10">
            {/* Beat Player */}
            {sessionData?.beatFile && (
              <div className="w-full max-w-2xl">
                <audio controls src={sessionData.beatFile} autoPlay loop className="w-full opacity-70" />
              </div>
            )}

            <div className="w-full max-w-2xl space-y-6">
              <div className="icon-wrapper text-6xl text-center mb-4">
                📝
              </div>

              <div>
                <label className="block text-xs text-studio-white/60 font-montserrat mb-2">
                  Song theme (optional)
                </label>
                <input
                  type="text"
                  value={theme}
                  onChange={(e) => setTheme(e.target.value)}
                  className="w-full px-4 py-3 bg-studio-gray/50 border border-studio-white/20 rounded-lg
                           text-studio-white font-poppins focus:outline-none focus:border-studio-red"
                  placeholder="success, love, struggle..."
                />
              </div>

              <motion.button
                onClick={handleGenerateLyrics}
                disabled={loading || (!sessionData?.beatFile && !theme?.trim())}
                className="w-full py-4 bg-studio-red hover:bg-studio-red/80 disabled:bg-studio-gray
                         text-studio-white font-montserrat font-semibold rounded-lg"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                {loading ? 'Generating...' : 'Generate Lyrics'}
              </motion.button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-8 p-6 md:p-10">
            {/* Beat Player */}
            {sessionData.beatFile && (
              <div className="w-full max-w-2xl">
                <audio controls src={sessionData.beatFile} className="w-full opacity-70" />
              </div>
            )}
            
            <div className="w-full max-w-2xl space-y-6">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
                className="bg-studio-gray/30 rounded-lg border border-studio-white/10 p-8 text-center"
              >
                {typeof lyrics === 'string' ? (
                  <div className="space-y-2">
                    {lyrics.split('\n').map((line, idx, arr) => {
                      // V18.1: Format options detection
                      const optionMatch = line.match(/^(Option\s+\d+):?\s*(.*)$/i);
                      // Check if there's a previous option before this one
                      const hasPreviousOption = idx > 0 && arr.slice(0, idx).some(l => l.match(/^Option\s+\d+/i));
                      
                      if (optionMatch) {
                        return (
                          <React.Fragment key={idx}>
                            {hasPreviousOption && <br />}
                            <p className="text-sm text-studio-white/90 font-poppins leading-relaxed">
                              <strong>{optionMatch[1]}</strong>
                              {optionMatch[2] && ` ${optionMatch[2]}`}
                            </p>
                          </React.Fragment>
                        );
                      }
                      return (
                        <p key={idx} className="text-sm text-studio-white/90 font-poppins leading-relaxed">
                          {line || '\u00A0'}
                        </p>
                      );
                    })}
                  </div>
                ) : (
                  <div className="space-y-8">
                    {lyrics.verse && (
                      <div className="lyrics-section">
                        <h3 className="text-lg text-studio-gold font-montserrat font-semibold mb-4">Verse</h3>
                        <div className="space-y-2">
                          {lyrics.verse.split('\n').map((line, idx) => (
                            <p key={idx} className="text-sm text-studio-white/90 font-poppins leading-relaxed">
                              {line || '\u00A0'}
                            </p>
                          ))}
                        </div>
                      </div>
                    )}
                    {lyrics.chorus && (
                      <div className="lyrics-section">
                        <h3 className="text-lg text-studio-gold font-montserrat font-semibold mb-4">Chorus</h3>
                        <div className="space-y-2">
                          {lyrics.chorus.split('\n').map((line, idx) => (
                            <p key={idx} className="text-sm text-studio-white/90 font-poppins leading-relaxed">
                              {line || '\u00A0'}
                            </p>
                          ))}
                        </div>
                      </div>
                    )}
                    {lyrics.bridge && (
                      <div className="lyrics-section">
                        <h3 className="text-lg text-studio-gold font-montserrat font-semibold mb-4">Bridge</h3>
                        <div className="space-y-2">
                          {lyrics.bridge.split('\n').map((line, idx) => (
                            <p key={idx} className="text-sm text-studio-white/90 font-poppins leading-relaxed">
                              {line || '\u00A0'}
                            </p>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </motion.div>
              
              <div className="w-full max-w-2xl space-y-4">
                <div>
                  <label className="block text-xs text-studio-white/60 font-montserrat mb-2">
                    Refine lyrics (give instructions)
                  </label>
                  <textarea
                    value={refineText}
                    onChange={(e) => setRefineText(e.target.value)}
                    className="w-full px-4 py-3 bg-studio-gray/50 border border-studio-white/20 rounded-lg
                             text-studio-white font-poppins focus:outline-none focus:border-studio-red
                             resize-none"
                    rows={3}
                    placeholder="e.g., rewrite the hook, make it darker, add more emotion..."
                  />
                </div>
                
                <motion.button
                  onClick={handleRefineLyrics}
                  disabled={loading || !refineText}
                  className="w-full py-3 px-6 bg-studio-red hover:bg-studio-red/80 disabled:bg-studio-gray
                           text-studio-white font-montserrat font-semibold rounded-lg"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  {loading ? 'Refining...' : 'Refine Lyrics'}
                </motion.button>
              </div>
              
              <motion.button
                onClick={() => setLyrics(null)}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
                className="w-full py-3 px-6 bg-studio-gray hover:bg-studio-gray/80
                         text-studio-white font-montserrat rounded-lg"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                Clear Lyrics
              </motion.button>
            </div>
          </div>
        )}
      </div>
    </StageWrapper>
  );
}

