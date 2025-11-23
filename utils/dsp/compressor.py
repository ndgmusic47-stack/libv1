import numpy as np


def apply_compressor(audio_data, threshold=-18, ratio=4.0, attack=5, release=50):
    """
    Basic RMS compressor.
    threshold in dB
    ratio > 1
    attack/release in ms
    """
    sr = 44100
    atk = np.exp(-1.0 / (sr * (attack / 1000)))
    rel = np.exp(-1.0 / (sr * (release / 1000)))

    out = np.zeros_like(audio_data)
    env = 0.0
    linear_threshold = 10 ** (threshold / 20)

    for i, sample in enumerate(audio_data):
        abs_sample = abs(sample)
        if abs_sample > env:
            env = atk * env + (1 - atk) * abs_sample
        else:
            env = rel * env + (1 - rel) * abs_sample

        if env > linear_threshold:
            gain = (linear_threshold + (env - linear_threshold) / ratio) / env
        else:
            gain = 1.0

        out[i] = sample * gain

    return out

