import { useEffect, useState } from "react";

interface TransportState {
  is_playing: boolean;
  position: number;
  duration: number;
}

export function useTransport(jobId: string) {
  const [state, setState] = useState<TransportState>({
    is_playing: false,
    position: 0,
    duration: 0,
  });

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/mix/transport/${jobId}`);

    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        setState({
          is_playing: data.is_playing,
          position: data.position,
          duration: data.duration,
        });
      } catch (err) {
        console.error("Transport WS parse error", err);
      }
    };

    return () => ws.close();
  }, [jobId]);

  // REST controls
  async function play() {
    await fetch(`/api/mix/transport/${jobId}/play`, { method: "POST" });
  }

  async function pause() {
    await fetch(`/api/mix/transport/${jobId}/pause`, { method: "POST" });
  }

  async function stop() {
    await fetch(`/api/mix/transport/${jobId}/stop`, { method: "POST" });
  }

  async function seek(position: number) {
    await fetch(`/api/mix/transport/${jobId}/seek`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(position),
    });
  }

  // Derived playhead ratio for timeline
  const playheadRatio = state.duration > 0 ? state.position / state.duration : 0;

  // derived pixel offset helper for future zoom/pan
  const getPixelFromRatio = (ratio: number, width: number) => ratio * width;

  return {
    ...state,
    play,
    pause,
    stop,
    seek,
    playheadRatio,
    getPixelFromRatio,
  };
}

