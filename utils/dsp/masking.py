import numpy as np


def detect_masking(vocal: np.ndarray, beat: np.ndarray, sr: int = 44100):
    """
    Returns frequency bins where masking occurs.
    """
    v_freqs = np.fft.rfftfreq(len(vocal), 1/sr)
    v_spec = np.abs(np.fft.rfft(vocal))
    b_spec = np.abs(np.fft.rfft(beat))

    # Masking = where beat energy greatly exceeds vocal in vocal-sensitive bands
    mask_band = (v_freqs > 150) & (v_freqs < 7000)
    masking = (b_spec[mask_band] > (v_spec[mask_band] * 1.8))

    return v_freqs[mask_band][masking]




def resolve_masking(beat: np.ndarray, masked_freqs: np.ndarray, amount: float = 0.18, sr: int = 44100):
    """
    Applies selective attenuation to masking frequencies.
    """
    freqs = np.fft.rfftfreq(len(beat), 1/sr)
    spectrum = np.fft.rfft(beat)


    for f in masked_freqs:
        idx = np.argmin(np.abs(freqs - f))
        spectrum[idx] *= (1 - amount)


    output = np.fft.irfft(spectrum, len(beat))
    return np.clip(output.astype(np.float32), -1.0, 1.0)

