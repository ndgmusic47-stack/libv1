import numpy as np


def apply_saturation(audio_data, amount=0.5):
    """
    Soft clipping saturation.
    amount: 0.0–1.0
    """
    k = amount * 10  
    return np.tanh(k * audio_data) / np.tanh(k)

