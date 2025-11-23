import { useEffect, useRef, useState } from "react";

interface PCMChunk {
  l: number[];
  r: number[];
  index: number;
}

export function useWaveformBuffer(jobId: string) {
  const [waveform, setWaveform] = useState<number[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const pendingRef = useRef<number[]>([]);

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/mix/stream/${jobId}/post_master`);
    wsRef.current = ws;

    ws.onmessage = (evt) => {
      try {
        const chunk: PCMChunk = JSON.parse(evt.data);
        pendingRef.current.push(...chunk.l);
      } catch (err) {
        console.error("Waveform chunk parse error", err);
      }
    };

    const interval = setInterval(() => {
      if (pendingRef.current.length > 0) {
        setWaveform((prev) => [...prev, ...pendingRef.current]);
        pendingRef.current = [];
      }
    }, 50);

    return () => {
      ws.close();
      clearInterval(interval);
    };
  }, [jobId]);

  return waveform;
}

