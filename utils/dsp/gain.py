import numpy as np


def apply_gain(audio_data, gain_db=0.0):
    factor = 10 ** (gain_db / 20)
    return audio_data * factor

