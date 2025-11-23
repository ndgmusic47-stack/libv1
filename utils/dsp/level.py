import numpy as np

def rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))))

def lufs(samples: np.ndarray) -> float:
    # Simple LUFS approximation (ITU BS.1770 weighting optional)
    if samples.size == 0:
        return -999.0
    mean_square = np.mean(samples ** 2)
    return -0.691 + 10 * np.log10(mean_square + 1e-12)

def match_loudness(samples: np.ndarray, target_lufs: float) -> float:
    current = lufs(samples)
    diff = target_lufs - current
    # convert LUFS diff to gain multiplier
    gain = 10 ** (diff / 20)
    return gain

def match_rms(samples: np.ndarray, target_rms: float) -> float:
    current = rms(samples)
    if current <= 0:
        return 1.0
    return float(target_rms / current)

def auto_gain(samples: np.ndarray, target_lufs: float, target_rms: float):
    g_lufs = match_loudness(samples, target_lufs)
    g_rms = match_rms(samples, target_rms)
    # Blend for stability
    return (g_lufs * 0.7) + (g_rms * 0.3)

