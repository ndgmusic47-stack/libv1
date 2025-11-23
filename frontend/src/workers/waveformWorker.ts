self.onmessage = (event) => {
  const { width, height, zoom, offset, tracks } = event.data;

  const canvas = new OffscreenCanvas(width, height);
  const ctx = canvas.getContext("2d")!;

  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, width, height);

  // Each track gets a vertical slice
  const trackNames = Object.keys(tracks);
  const perTrackHeight = height / trackNames.length;

  const colors: Record<string, string> = {
    beat: "#4b9eff",
    vocal: "#ff4bb8",
    master: "#ffd34b",
  };

  for (let t = 0; t < trackNames.length; t++) {
    const name = trackNames[t];
    const waveform = tracks[name];

    if (!waveform?.length) continue;

    const yOffset = t * perTrackHeight;
    const h = perTrackHeight;

    const windowSize = width * zoom;
    const start = Math.max(0, offset);
    const end = Math.min(start + windowSize, waveform.length);

    const count = end - start;
    const spp = Math.max(1, Math.floor(count / width));

    ctx.strokeStyle = colors[name] || "#6cf";
    ctx.beginPath();

    for (let x = 0; x < width; x++) {
      const base = start + x * spp;
      if (base >= end) break;

      let min = 1.0;
      let max = -1.0;

      for (let i = 0; i < spp && base + i < end; i++) {
        const v = waveform[base + i];
        if (v < min) min = v;
        if (v > max) max = v;
      }

      const y1 = yOffset + ((1 - max) * h) / 2;
      const y2 = yOffset + ((1 - min) * h) / 2;
      ctx.moveTo(x, y1);
      ctx.lineTo(x, y2);
    }

    ctx.stroke();
  }

  const bitmap = canvas.transferToImageBitmap();
  self.postMessage({ bitmap }, [bitmap]);
};

