import { useState, useCallback } from "react";

export function useTimelineZoomPan() {
  const [zoom, setZoom] = useState(1);    // multiplier: 1,2,4,8...
  const [offset, setOffset] = useState(0); // in samples

  const zoomIn = useCallback(() => setZoom((z) => Math.min(z * 2, 64)), []);
  const zoomOut = useCallback(() => setZoom((z) => Math.max(z / 2, 1)), []);

  const panLeft = useCallback(() => setOffset((o) => Math.max(o - 2000 * zoom, 0)), [zoom]);
  const panRight = useCallback(
    (bufferLength: number) =>
      setOffset((o) => Math.min(o + 2000 * zoom, Math.max(bufferLength - 1, 0))),
    [zoom]
  );

  return {
    zoom,
    offset,
    zoomIn,
    zoomOut,
    panLeft,
    panRight,
  };
}

