import React, { useEffect, useRef } from "react";

// @ts-ignore — worker import via Vite
import WaveformWorker from "../../workers/waveformWorker.ts?worker";

export function WaveformCanvas({
  tracks,
  zoom,
  offset,
}: {
  tracks: Record<string, number[]>;
  zoom: number;
  offset: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const workerRef = useRef<Worker | null>(null);

  useEffect(() => {
    if (!workerRef.current) {
      workerRef.current = new WaveformWorker();
    }
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !workerRef.current) return;

    const width = canvas.width;
    const height = canvas.height;

    workerRef.current.onmessage = (evt) => {
      const { bitmap } = evt.data;
      if (!bitmap) return;

      const ctx = canvas.getContext("bitmaprenderer")!;
      ctx.transferFromImageBitmap(bitmap);
    };

    workerRef.current.postMessage({
      tracks,
      width,
      height,
      zoom,
      offset,
    });
  }, [tracks, zoom, offset]);

  return (
    <canvas
      ref={canvasRef}
      width={1000}
      height={200}
      style={{ width: "100%", height: 200, background: "#000" }}
    />
  );
}
