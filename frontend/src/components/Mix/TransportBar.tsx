import React from "react";
import { useTransport } from "../../hooks/useTransport";

export function TransportBar({ jobId }: { jobId: string }) {
  const { is_playing, position, duration, play, pause, stop, seek } =
    useTransport(jobId);

  return (
    <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
      <button onClick={play}>Play</button>
      <button onClick={pause}>Pause</button>
      <button onClick={stop}>Stop</button>

      <input
        type="range"
        min={0}
        max={duration}
        value={position}
        step={0.01}
        onChange={(e) => seek(parseFloat(e.target.value))}
        style={{ width: 300 }}
      />

      <span>{position.toFixed(2)} / {duration.toFixed(2)}</span>
    </div>
  );
}

