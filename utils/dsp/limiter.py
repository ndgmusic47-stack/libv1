import numpy as np


def apply_limiter(audio_data, ceiling=-1.0):
    """
    Simple peak limiter.
    ceiling in dBFS
    """
    linear_ceiling = 10 ** (ceiling / 20)
    peak = np.max(np.abs(audio_data))

    if peak > linear_ceiling:
        audio_data = audio_data * (linear_ceiling / peak)

    return audio_data

