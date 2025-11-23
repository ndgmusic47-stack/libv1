import numpy as np

def spectral_tilt(samples: np.ndarray, tilt: float = 0.10):
    """
    Applies a gentle tilt EQ: boosts highs slightly & reduces lows slightly.
    Positive tilt brightens; negative tilt darkens.
    """
    freqs = np.fft.rfftfreq(len(samples), 1/44100)
    spectrum = np.fft.rfft(samples)

    tilt_curve = 1 + (tilt * (freqs / freqs.max()))
    spectrum *= tilt_curve

    output = np.fft.irfft(spectrum, len(samples))
    return output.astype(np.float32)

def low_mid_cleanup(samples: np.ndarray, amount: float = 0.12):
    """
    Reduces 200–450 Hz mud region.
    """
    freqs = np.fft.rfftfreq(len(samples), 1/44100)
    spectrum = np.fft.rfft(samples)

    mask = (freqs > 180) & (freqs < 450)
    spectrum[mask] *= (1 - amount)

    output = np.fft.irfft(spectrum, len(samples))
    return output.astype(np.float32)

def presence_boost(samples: np.ndarray, amount: float = 0.10):
    """
    Adds upper-mid presence without harshness.
    2.5–5 kHz.
    """
    freqs = np.fft.rfftfreq(len(samples), 1/44100)
    spectrum = np.fft.rfft(samples)

    mask = (freqs > 2500) & (freqs < 5000)
    spectrum[mask] *= (1 + amount)

    output = np.fft.irfft(spectrum, len(samples))
    return output.astype(np.float32)

def tonal_balance_chain(samples: np.ndarray, role: str):
    """
    Applies role-aware tonal shaping.
    """
    # Lead vocals — bright but smooth
    if role in ["lead_vocal", "lead", "main_vocal"]:
        samples = spectral_tilt(samples, tilt=0.12)
        samples = low_mid_cleanup(samples, amount=0.15)
        samples = presence_boost(samples, amount=0.10)

    # Adlibs/backing — lighter shaping
    elif role in ["adlib", "backing_vocal"]:
        samples = spectral_tilt(samples, tilt=0.10)
        samples = presence_boost(samples, amount=0.07)

    # Beat — clean low-mids, preserve punch
    elif role in ["beat", "drums", "kick", "snare"]:
        samples = low_mid_cleanup(samples, amount=0.10)
        samples = spectral_tilt(samples, tilt=0.08)

    # Default
    else:
        samples = spectral_tilt(samples, tilt=0.08)
        samples = low_mid_cleanup(samples, amount=0.12)

    return np.clip(samples, -1.0, 1.0)
