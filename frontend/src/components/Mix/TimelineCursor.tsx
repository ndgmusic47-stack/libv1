import React from "react";

export function TimelineCursor({
  playheadRatio,
  zoom,
  offset,
  waveformLength,
}: {
  playheadRatio: number;
  zoom: number;
  offset: number;
  waveformLength: number;
}) {
  // Convert playhead ratio → pixel position inside zoomed window
  const playheadSample = playheadRatio * waveformLength;

  const windowStart = offset;
  const windowEnd = offset + 1000 * zoom;

  let leftPct = 0;

  if (playheadSample >= windowStart && playheadSample <= windowEnd) {
    const relative = playheadSample - windowStart;
    leftPct = relative / (windowEnd - windowStart);
  } else {
    // playhead out of view
    leftPct = -10; // hide left
  }

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        bottom: 0,
        width: 2,
        background: "red",
        left: `${leftPct * 100}%`,
        pointerEvents: "none",
      }}
    />
  );
}

