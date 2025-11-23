import { useEffect, useRef } from "react";

export function useAudioEngine() {
  const audioCtxRef = useRef<AudioContext | null>(null);
  const masterGainRef = useRef<GainNode | null>(null);

  if (!audioCtxRef.current) {
    const ctx = new AudioContext();
    const gain = ctx.createGain();
    gain.gain.value = 1.0;
    gain.connect(ctx.destination);

    audioCtxRef.current = ctx;
    masterGainRef.current = gain;
  }

  return {
    audioCtx: audioCtxRef.current!,
    masterGain: masterGainRef.current!,
  };
}

