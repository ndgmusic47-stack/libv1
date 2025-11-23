import numpy as np


def chunk_audio(audio, chunk_size=2048):
    """
    Splits a stereo numpy array into sequential chunks for real-time streaming.
    Returns:
        [
            {
                "l": [...],
                "r": [...],
                "index": int
            },
            ...
        ]
    """
    length = audio.shape[0]
    chunks = []

    index = 0
    for i in range(0, length, chunk_size):
        window = audio[i:i+chunk_size]
        if len(window) == 0:
            break

        # pad if needed
        if window.shape[0] < chunk_size:
            pad_len = chunk_size - window.shape[0]
            pad = np.zeros((pad_len, audio.shape[1]), dtype=audio.dtype)
            window = np.vstack([window, pad])

        chunks.append({
            "index": index,
            "l": window[:, 0].astype(np.float32).tolist(),
            "r": window[:, 1].astype(np.float32).tolist(),
        })

        index += 1

    return chunks

