// Use backend proxy via Vite dev server
const API_BASE = '/api';

// Helper to normalize media URLs consistently
export const normalizeMediaUrl = (url) => {
  if (!url) return url;

  if (url.startsWith('/api/media/')) return url;

  if (url.startsWith('/media/')) {
    // Helper to strip trailing /api or /api/ from API_BASE
    const stripApiSuffix = (base) => {
      if (base.endsWith('/api/')) return base.slice(0, -5);
      if (base.endsWith('/api')) return base.slice(0, -4);
      return base;
    };

    // If API_BASE is absolute (starts with http:// or https://), derive backend origin
    if (API_BASE.startsWith('http://') || API_BASE.startsWith('https://')) {
      const backendOrigin = stripApiSuffix(API_BASE);
      return `${backendOrigin}${url}`;
    }

    // If API_BASE is relative, return url unchanged
    return url;
  }

  return url;
};

// Phase 2.2: Helper to handle standardized JSON responses {ok, data, message} or {ok, error}
// Phase 8.4: Preserve error data for paywall checks
const handleResponse = async (response) => {
 // First check HTTP status
 if (!response.ok) {
   const result = await response.json().catch(() => ({}));
   
   // Handle 400 errors gracefully
   if (response.status === 400) {
     return { ok: false, error: result.message || result.error || "Invalid email or password" };
   }
   
   const error = new Error(result.detail || result.message || result.error || 'API request failed');
   error.status = response.status;
   // Phase 8.4: For upgrade_required errors, attach full error data to error object
   if (result.error === "upgrade_required") {
     error.errorData = result;
     error.isPaywall = true;
   }
   throw error;
 }

 const result = await response.json().catch(() => ({}));

 // Phase 8.4: Check for paywall errors even if response.ok is true (in case backend returns 403 but ok: false)
 if (!result.ok) {
   // Phase 8.4: For upgrade_required errors, attach full error data to error object
   const error = new Error(result.error || result.message || result.detail || 'API request failed');
   error.status = response.status;
   if (result.error === "upgrade_required") {
     error.errorData = result;
     error.isPaywall = true;
   }
   throw error;
 }

 // Return data directly for easier consumption
 return result.data || result;
};

export const api = {
 // ========== V4 PROJECT MEMORY ==========

 listProjects: async () => {
   const response = await fetch(`${API_BASE}/projects`, {
     credentials: "include"
   });
   return response.json();
 },

 getProject: async (sessionId) => {
   const response = await fetch(`${API_BASE}/projects/${sessionId}`, {
     credentials: "include"
   });
   const result = await response.json();
   if (!result.ok) {
     throw new Error(result.error || 'Failed to get project');
   }
   return result.project || result;
 },


 // ========== V4 REFERENCE ENGINE ==========

 analyzeReference: async (sessionId, file = null, spotifyUrl = null) => {
   const formData = new FormData();
   formData.append('session_id', sessionId);
   if (file) formData.append('file', file);
   if (spotifyUrl) formData.append('spotify_url', spotifyUrl);

   const response = await fetch(`${API_BASE}/reference/analyze`, {
     method: 'POST',
     credentials: "include",
     body: formData,
   });
   return response.json();
 },

 // ========== EXISTING ENDPOINTS ==========

 createBeat: async (promptText, mood, genre = 'hip hop', sessionId = null) => {
   const body = {
     prompt: promptText,
     mood,
     genre,
     session_id: sessionId,
   };
   const response = await fetch(`${API_BASE}/beats/create`, {
     method: 'POST',
     credentials: "include",
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify(body),
   });
   return handleResponse(response);
 },

 getBeatCredits: async () => {
   const response = await fetch(`${API_BASE}/beats/credits`, {
     credentials: "include"
   });
   return handleResponse(response);
 },

generateLyrics: async (genre, mood, theme = '', sessionId = null) => {
  const response = await fetch(`${API_BASE}/lyrics/songs/write`, {
     method: 'POST',
     credentials: "include",
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({
       genre,
       mood,
       theme,
       session_id: sessionId,
     }),
   });
   return handleResponse(response);
 },

 // V17: Generate lyrics from beat
 // V18.2: Accepts either File object or FormData object
 generateLyricsFromBeat: async (fileOrFormData, sessionId = null) => {
   let body = fileOrFormData instanceof FormData 
     ? fileOrFormData 
     : (() => { const fd = new FormData(); fd.append("file", fileOrFormData); return fd; })();
   
   if (sessionId) {
     body.append('session_id', sessionId);
   }
   
   const response = await fetch(`${API_BASE}/lyrics/from_beat`, {
     method: 'POST',
     credentials: "include",
     body,
   });
   return handleResponse(response);
 },

 // V17: Generate free lyrics from theme
 generateFreeLyrics: async (theme, sessionId = null) => {
   const response = await fetch(`${API_BASE}/lyrics/free`, {
     method: 'POST',
     credentials: "include",
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({ theme, session_id: sessionId }),
   });
   return handleResponse(response);
 },

 // V18.1: Refine lyrics based on user instruction with history and metadata
 refineLyrics: async (lyricsText, instruction, bpm = null, history = [], structuredLyrics = null, rhythmMap = null, sessionId = null) => {
   const response = await fetch(`${API_BASE}/lyrics/refine`, {
     method: 'POST',
     credentials: "include",
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({ 
       lyrics: lyricsText, 
       instruction, 
       bpm,
       history,
       structured_lyrics: structuredLyrics,
       rhythm_map: rhythmMap,
       session_id: sessionId
     }),
   });
   return handleResponse(response);
 },

 uploadRecording: async (file, sessionId = null) => {
   const formData = new FormData();
   formData.append('file', file);
   if (sessionId) formData.append('session_id', sessionId);

   const response = await fetch(`${API_BASE}/media/upload/vocal`, {
     method: "POST",
     credentials: "include",
     body: formData,
   });
   return handleResponse(response);
 },




  // NEW RELEASE MODULE ENDPOINTS
  generateReleaseCover: async (projectId, trackTitle, artistName, genre, mood, style = 'realistic') => {
    const response = await fetch(`${API_BASE}/projects/${projectId}/release/cover`, {
      method: 'POST',
      credentials: "include",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: projectId,
        track_title: trackTitle,
        artist_name: artistName,
        genre,
        mood,
        style,
      }),
    });
    return handleResponse(response);
  },

  selectReleaseCover: async (projectId, coverUrl) => {
    const response = await fetch(`${API_BASE}/projects/${projectId}/release/select-cover`, {
      method: 'POST',
      credentials: "include",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: projectId,
        cover_url: coverUrl,
      }),
    });
    return handleResponse(response);
  },

  listReleaseFiles: async (projectId) => {
    const response = await fetch(`${API_BASE}/projects/${projectId}/release/files`, {
      method: 'GET',
      credentials: "include",
      headers: { 'Content-Type': 'application/json' },
    });
    const result = await handleResponse(response);
    return result.data || result;
  },

  getReleasePack: async (projectId) => {
    const response = await fetch(`${API_BASE}/projects/${projectId}/release/pack`, {
      method: 'GET',
      credentials: "include",
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse(response);
  },

  generateReleaseCopy: async (projectId, trackTitle, artistName, genre, mood, lyrics = '') => {
    const response = await fetch(`${API_BASE}/projects/${projectId}/release/copy`, {
      method: 'POST',
      credentials: "include",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: projectId,
        track_title: trackTitle,
        artist_name: artistName,
        genre,
        mood,
        lyrics,
      }),
    });
    return handleResponse(response);
  },

  generateLyricsPDF: async (projectId, title, artist, lyrics) => {
    const response = await fetch(`${API_BASE}/projects/${projectId}/release/lyrics`, {
      method: 'POST',
      credentials: "include",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: projectId,
        title,
        artist,
        lyrics,
      }),
    });
    return handleResponse(response);
  },

  generateReleaseMetadata: async (projectId, trackTitle, artistName, mood, genre, explicit, releaseDate) => {
    const response = await fetch(`${API_BASE}/projects/${projectId}/release/metadata`, {
      method: 'POST',
      credentials: "include",
      headers: { 
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        session_id: projectId,
        track_title: trackTitle,
        artist_name: artistName,
        mood,
        genre,
        explicit,
        release_date: releaseDate,
      }),
    });
    return handleResponse(response);
  },

  downloadAllReleaseFiles: async (projectId) => {
    const response = await fetch(`${API_BASE}/projects/${projectId}/release/download-all`, {
      method: 'POST',
      credentials: "include",
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse(response);
  },



  // V23.1: LEGACY - Old caption generator removed
  // generateContent: async (title, artist, sessionId = null) => {
  //   const response = await fetch(`${API_BASE}/content/ideas`, {
  //     method: 'POST',
  //     headers: { 'Content-Type': 'application/json' },
  //     body: JSON.stringify({
  //       session_id: sessionId,
  //       title,
  //       artist,
  //     }),
  //   });
  //   return handleResponse(response);
  // },

  // V23: ContentStage MVP endpoints
  generateVideoIdea: async (sessionId, title, lyrics, mood, genre) => {
    const response = await fetch(`${API_BASE}/content/idea`, {
      method: 'POST',
      credentials: "include",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        title,
        lyrics,
        mood,
        genre,
      }),
    });
    return handleResponse(response);
  },

  uploadVideo: async (file, sessionId) => {
    const formData = new FormData();
    formData.append('file', file);
    if (sessionId) formData.append('session_id', sessionId);

    const response = await fetch(`${API_BASE}/content/upload-video`, {
      method: 'POST',
      credentials: "include",
      body: formData,
    });
    return handleResponse(response);
  },

  analyzeVideo: async (transcript, title, lyrics, mood, genre) => {
    const response = await fetch(`${API_BASE}/content/analyze`, {
      method: 'POST',
      credentials: "include",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        transcript,
        title,
        lyrics,
        mood,
        genre,
      }),
    });
    return handleResponse(response);
  },

  generateContentText: async (sessionId, title, transcript, lyrics, mood, genre) => {
    const response = await fetch(`${API_BASE}/content/generate-text`, {
      method: 'POST',
      credentials: "include",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        title,
        transcript,
        lyrics,
        mood,
        genre,
      }),
    });
    return handleResponse(response);
  },

  scheduleVideo: async (sessionId, videoUrl, caption, hashtags, platform, scheduleTime) => {
    const response = await fetch(`${API_BASE}/content/schedule`, {
      method: 'POST',
      credentials: "include",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        video_url: videoUrl,
        caption,
        hashtags: hashtags || [],
        platform: platform || 'tiktok',
        schedule_time: scheduleTime,
      }),
    });
    return handleResponse(response);
  },

  saveScheduled: async (data) => {
    const response = await fetch(`${API_BASE}/content/save-scheduled`, {
      method: 'POST',
      credentials: "include",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return handleResponse(response);
  },

  getScheduled: async (sessionId) => {
    const response = await fetch(`${API_BASE}/content/get-scheduled?session_id=${sessionId}`, {
      method: 'GET',
      credentials: "include",
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse(response);
  },


 // ========== ANALYTICS ==========

 getProjectAnalytics: async (sessionId) => {
   const response = await fetch(`${API_BASE}/analytics/session/${sessionId}`, {
     credentials: "include"
   });
   return handleResponse(response);
 },

 getDashboardAnalytics: async () => {
   const response = await fetch(`${API_BASE}/analytics/dashboard/all`, {
     credentials: "include"
   });
   return handleResponse(response);
 },

 updateAnalytics: async (sessionId, streams = null, revenue = null, saves = null, shares = null) => {
   const formData = new FormData();
   formData.append('session_id', sessionId);
   if (streams !== null) formData.append('streams', streams);
   if (revenue !== null) formData.append('revenue', revenue);
   if (saves !== null) formData.append('saves', saves);
   if (shares !== null) formData.append('shares', shares);

   const response = await fetch(`${API_BASE}/analytics/update`, {
     method: 'POST',
     credentials: "include",
     body: formData,
   });
   return response.json();
 },

 analyzeVideoBeats: async (formData) => {
   const response = await fetch(`${API_BASE}/video/analyze`, {
     method: 'POST',
     credentials: "include",
     body: formData,
   });
   return response.json();
 },

 createBeatSyncVideo: async (sessionId, style = 'energetic', outputName = 'beat_sync_video.mp4') => {
   const formData = new FormData();
   formData.append('session_id', sessionId);
   formData.append('style', style);
   formData.append('output_name', outputName);

   const response = await fetch(`${API_BASE}/video/beat-sync`, {
     method: 'POST',
     credentials: "include",
     body: formData,
   });
   return response.json();
 },

 exportVideo: async (sessionId, format = 'mp4', quality = 'high', resolution = null) => {
   const formData = new FormData();
   formData.append('session_id', sessionId);
   formData.append('format', format);
   formData.append('quality', quality);
   if (resolution) formData.append('resolution', resolution);

   const response = await fetch(`${API_BASE}/video/export`, {
     method: 'POST',
     credentials: "include",
     body: formData,
   });
   return response.json();
 },

 getSocialPlatforms: async () => {
   const response = await fetch(`${API_BASE}/social/platforms`, {
     credentials: "include"
   });
   return handleResponse(response);
 },

  schedulePost: async (sessionId, platform, caption, whenIso) => {
    const response = await fetch(`${API_BASE}/social/posts`, {
      method: 'POST',
      credentials: "include",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        platform,
        caption,
        when_iso: whenIso,
      }),
    });
    return handleResponse(response);
  },


 getScheduledPosts: async (sessionId, platform = null) => {
   const url = platform
     ? `${API_BASE}/social/posts/${sessionId}?platform=${platform}`
     : `${API_BASE}/social/posts/${sessionId}`;
   const response = await fetch(url, {
     credentials: "include"
   });
   return response.json();
 },

 cancelPost: async (sessionId, postId) => {
   const formData = new FormData();
   formData.append('session_id', sessionId);
   formData.append('post_id', postId);

   const response = await fetch(`${API_BASE}/social/cancel`, {
     method: 'POST',
     credentials: "include",
     body: formData,
   });
   return response.json();
 },

 getOptimalTimes: async (platform, timezone = 'EST') => {
   const response = await fetch(`${API_BASE}/social/optimal-times/${platform}?timezone=${timezone}`, {
     credentials: "include"
   });
   return response.json();
 },

 processIntent: async (sessionId, command) => {
   const formData = new FormData();
   formData.append('session_id', sessionId);
   formData.append('command', command);

   const response = await fetch(`${API_BASE}/intent`, {
     method: 'POST',
     credentials: "include",
     body: formData,
   });
   return response.json();
 },

 // ========== SYNC PROJECT HELPER ==========
 
 syncProject: async (sessionId, updateSessionData) => {
   try {
     const project = await api.getProject(sessionId);
     if (!project) return;
     
     const updates = {};
     
     // Sync assets according to spec
     if (project.assets) {
       // Beat file from project.assets.beat.url
       if (project.assets.beat?.url) {
         updates.beatFile = project.assets.beat.url;
       }
       
      // Vocal file - prioritize project.assets.vocals[0], fallback to project.assets.stems[0]
      if (project.assets.vocals && project.assets.vocals.length > 0) {
        const vocal = project.assets.vocals[0];
        const chosenValue = vocal.url || vocal.path;
        if (chosenValue) {
          updates.vocalFile = normalizeMediaUrl(chosenValue);
        }
      } else if (project.assets.stems && project.assets.stems.length > 0 && project.assets.stems[0]?.url) {
        // Fallback to stems for backward compatibility
        updates.vocalFile = normalizeMediaUrl(project.assets.stems[0].url);
      }
       
       // Mix file from project.assets.mix?.url
       if (project.assets.mix?.url) {
         updates.mixFile = project.assets.mix.url;
       }
       
       // Master file from project.assets.master?.url
       if (project.assets.master?.url) {
         updates.masterFile = project.assets.master.url;
       }
       
      // Cover art (optional)
      if (project.assets.cover_art?.url) {
        updates.coverArt = project.assets.cover_art.url;
      }
      
      // Release pack (optional)
      if (project.assets.release_pack) {
        updates.releasePack = project.assets.release_pack;
      }
    }
     
     // Sync metadata
     if (project.metadata) {
       if (project.metadata.mood) updates.mood = project.metadata.mood;
       if (project.metadata.genre) updates.genre = project.metadata.genre;
       if (project.metadata.track_title) updates.trackTitle = project.metadata.track_title;
       if (project.metadata.artist_name) updates.artistName = project.metadata.artist_name;
     }
     
     // Sync lyrics
     if (project.lyrics?.text) {
       updates.lyricsData = project.lyrics.text;
     } else if (project.lyrics_text) {
       updates.lyricsData = project.lyrics_text;
     } else if (project.assets?.lyrics?.url) {
       // Fetch lyrics from URL if available
       try {
         const response = await fetch(project.assets.lyrics.url);
         if (response.ok) {
           const lyricsText = await response.text();
           updates.lyricsData = lyricsText;
         }
       } catch (err) {
         // Fail silently - don't crash syncProject
         console.warn('Failed to fetch lyrics from URL:', err);
       }
     }
     
     if (Object.keys(updates).length > 0 && updateSessionData) {
       updateSessionData(updates);
     }
     
     return updates;
   } catch (err) {
     console.error('Failed to sync project:', err);
     throw err;
   }
 },

 // ========== ADVANCE STAGE ==========
 
 advanceStage: async (sessionId) => {
   const response = await fetch(`${API_BASE}/projects/${sessionId}/advance`, {
     method: 'POST',
     credentials: "include",
     headers: { 'Content-Type': 'application/json' },
   });
   return handleResponse(response);
 },

 // ========== PROJECT SAVE/LOAD (PHASE 8.3) ==========

 saveProject: async (projectId, projectData) => {
   const response = await fetch(`${API_BASE}/projects/save`, {
     method: 'POST',
     credentials: "include",
     headers: { 
       'Content-Type': 'application/json'
     },
     body: JSON.stringify({
       projectId: projectId || null,
       projectData
     })
   });
   return handleResponse(response);
 },

 listProjects: async () => {
   const response = await fetch(`${API_BASE}/projects/list`, {
     credentials: "include"
   });
   return handleResponse(response);
 },

 loadProject: async (projectId) => {
   const response = await fetch(`${API_BASE}/projects/load`, {
     method: 'POST',
     credentials: "include",
     headers: { 
       'Content-Type': 'application/json'
     },
     body: JSON.stringify({ projectId })
   });
   return handleResponse(response);
 },

 // ========== BILLING (PHASE 9) ==========

 createCheckoutSession: async (email = null, priceId = null) => {
   const response = await fetch(`${API_BASE}/billing/create-checkout-session`, {
     method: 'POST',
     credentials: "include",
     headers: { 
       'Content-Type': 'application/json'
     },
     body: JSON.stringify({ email, priceId })
   });
   return handleResponse(response);
 },

 createPortalSession: async () => {
   const response = await fetch(`${API_BASE}/billing/portal`, {
     method: 'POST',
     credentials: "include",
     headers: { 
       'Content-Type': 'application/json'
     }
   });
   return handleResponse(response);
  },

  // ========== MIX JOB ENDPOINTS ==========
  startMix: async (projectId, config = {}) => {
    const response = await fetch(
      `${API_BASE}/projects/${projectId}/mix/start`,
      {
        method: 'POST',
        credentials: "include",
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config })
      }
    );
    const result = await handleResponse(response);
    return result; // expects { job_id }
  },
};

// Export standalone functions for convenience
export async function createCheckoutSession() {
  return api.createCheckoutSession();
}

export async function createPortalSession() {
  return api.createPortalSession();
}


// ========== DSP MIX JOB ENDPOINTS ==========

// Start a DSP mix job
export async function startMix(projectId, config = {}) {
  const response = await fetch(
    `${API_BASE}/projects/${projectId}/mix/start`,
    {
      method: 'POST',
      credentials: "include",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config })
    }
  );
  const result = await handleResponse(response);
  return result; // expects { job_id }
}

// Get mix job status
export async function getMixStatus(projectId, jobId) {
  const response = await fetch(
    `${API_BASE}/projects/${projectId}/mix/status?job_id=${jobId}`,
    {
      method: 'GET',
      credentials: "include"
    }
  );
  const result = await handleResponse(response);
  return result; // expects { state, mix_url? }
}

// Get mix preview URL
export async function getMixPreview(projectId) {
  const response = await fetch(
    `${API_BASE}/projects/${projectId}/mix/preview`,
    {
      method: 'GET',
      credentials: "include"
    }
  );
  const result = await handleResponse(response);
  return result; // expects { mix_url }
}