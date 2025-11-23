import numpy as np

def add_air(audio, gain_db=1.5, freq=12000):
    """
    Simple high-shelf air band.
    Applies a gentle high frequency boost.
    """
    factor = 10 ** (gain_db / 20)
    
    # High-frequency emphasis using sine kernel
    sr = 44100
    t = np.arange(audio.shape[0])
    kernel = np.sin(2 * np.pi * freq * t / sr)
    kernel = (kernel + 1) / 2  # normalize to 0-1
    
    airy = audio * (1 + (kernel[:,None] * (factor - 1)))
    
    # Normalize
    peak = np.max(np.abs(airy))
    if peak > 1:
        airy = airy / peak
    
    return airy

