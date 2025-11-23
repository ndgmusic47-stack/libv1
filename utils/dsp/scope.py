import numpy as np


def compute_scope(audio, window_size=2048, steps=200):
    """
    Returns a downsampled scrolling oscilloscope view.
    audio: stereo numpy array
    window_size: number of samples to look at at each step
    steps: number of segments returned
    
    Returns a list of dicts:
    [
        { "l": [...], "r": [...] },
        ...
    ]
    """
    length = audio.shape[0]
    hop = max(1, (length - window_size) // steps)

    scope_frames = []
    for i in range(0, steps * hop, hop):
        end = i + window_size
        if end > length:
            break
        window = audio[i:end]
        l = window[:, 0]
        r = window[:, 1]

        # Downsample each window to 256 samples
        idx = np.linspace(0, len(l)-1, 256).astype(np.int32)
        frame = {
            "l": l[idx].astype(np.float32).tolist(),
            "r": r[idx].astype(np.float32).tolist(),
        }
        scope_frames.append(frame)

    return scope_frames

