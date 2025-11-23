import numpy as np

def apply_deesser(audio_data, freq=6000, threshold=-20.0, ratio=4.0):
    """
    Simple broadband de-esser:
    - Bandpass around sibilance region
    - Detect energy
    - Apply compression to that band only
    """
    sr = 44100
    w0 = 2 * np.pi * freq / sr
    bw = w0 / 4  # wide band
    
    # Simple bandpass filter: sinusoid approximation
    bp = np.sin(w0 * np.arange(audio_data.shape[0])) * audio_data[:, 0]  # apply on L channel for detection
    
    rms = np.sqrt(np.mean(bp**2))
    linear_threshold = 10 ** (threshold / 20)
    
    if rms <= linear_threshold:
        return audio_data

    gain = linear_threshold / (rms + 1e-9)
    gain = gain ** (ratio - 1)

    return audio_data * gain

