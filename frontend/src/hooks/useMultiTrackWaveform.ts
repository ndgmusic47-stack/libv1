import { useEffect, useRef, useState } from "react";

interface PCMChunk {
  l: number[];
  r: number[];
  index: number;
}

export function useMultiTrackWaveform(jobId: string) {
  const [tracks, setTracks] = useState({
    beat: [] as number[],
    vocal: [] as number[],
    master: [] as number[],
  });

  const pending = useRef({
    beat: [] as number[],
    vocal: [] as number[],
    master: [] as number[],
  });

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/mix/stream/${jobId}/multi`);
    
    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);

        // expected shape:
        // { beat: { l:[] }, vocal:{ l:[] }, master:{ l:[] } }

        if (msg.beat?.l) pending.current.beat.push(...msg.beat.l);
        if (msg.vocal?.l) pending.current.vocal.push(...msg.vocal.l);
        if (msg.master?.l) pending.current.master.push(...msg.master.l);
      } catch {}
    };

    const interval = setInterval(() => {
      const p = pending.current;
      if (
        p.beat.length ||
        p.vocal.length ||
        p.master.length
      ) {
        setTracks((prev) => ({
          beat: [...prev.beat, ...p.beat],
          vocal: [...prev.vocal, ...p.vocal],
          master: [...prev.master, ...p.master],
        }));
        pending.current = { beat: [], vocal: [], master: [] };
      }
    }, 50);

    return () => {
      ws.close();
      clearInterval(interval);
    };
  }, [jobId]);

  return tracks;
}

