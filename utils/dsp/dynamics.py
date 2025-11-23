import numpy as np


def soften_transients(samples: np.ndarray, threshold: float = 0.15, soften_factor: float = 0.6):
    """
    Reduces sharp peaks while keeping punch.
    """
    peaks = np.abs(samples) > threshold
    samples[peaks] *= soften_factor
    return np.clip(samples, -1.0, 1.0)


def micro_compress(samples: np.ndarray, ratio: float = 1.3, attack: float = 0.0005, release: float = 0.005):
    """
    A transparent micro-compressor—very subtle.
    """
    gain = 1.0
    out = np.zeros_like(samples)

    for i in range(len(samples)):
        level = abs(samples[i])

        if level > 0.2:
            gain -= (level - 0.2) * (ratio - 1) * attack
        else:
            gain += release

        gain = max(min(gain, 1.0), 0.2)
        out[i] = samples[i] * gain

    return np.clip(out, -1.0, 1.0)


def smooth_vocals(samples: np.ndarray, smooth_factor: float = 0.08):
    """
    Light smoothing by blending each sample with neighbors.
    """
    if len(samples) < 3:
        return samples

    out = samples.copy()
    for i in range(1, len(samples)-1):
        out[i] = (
            samples[i] * (1 - smooth_factor) +
            (samples[i-1] + samples[i+1]) * (smooth_factor / 2)
        )
    return np.clip(out, -1.0, 1.0)

