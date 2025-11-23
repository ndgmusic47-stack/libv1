import numpy as np


def compute_waveform(audio, samples=2000):
    """
    Downsamples waveform for UI rendering.
    Returns float32 array length = samples.
    """
    length = audio.shape[0]
    idx = np.linspace(0, length - 1, samples).astype(np.int32)
    mono = audio.mean(axis=1)
    return mono[idx].astype(np.float32).tolist()


def compute_fft_spectrum(audio, bins=256):
    """
    Computes magnitude spectrum for visualization.
    Returns float32 array length = bins.
    """
    mono = audio.mean(axis=1)
    fft = np.fft.rfft(mono)
    mag = np.abs(fft)
    idx = np.linspace(0, len(mag) - 1, bins).astype(np.int32)
    sampled = mag[idx]
    norm = sampled / (np.max(sampled) + 1e-9)
    return norm.astype(np.float32).tolist()


def compute_levels(audio):
    """
    RMS + peak level.
    """
    mono = audio.mean(axis=1)
    rms = float(np.sqrt(np.mean(mono ** 2)))
    peak = float(np.max(np.abs(mono)))
    return {"rms": rms, "peak": peak}


def compute_energy_curve(audio, segments=128):
    """
    Computes a segment-based energy curve.
    """
    mono = audio.mean(axis=1)
    length = len(mono)
    seg_size = length // segments
    curve = []
    for i in range(segments):
        seg = mono[i * seg_size:(i + 1) * seg_size]
        if len(seg) > 0:
            curve.append(float(np.sqrt(np.mean(seg ** 2))))
        else:
            curve.append(0.0)
    return curve


def compute_track_spectrum(audio, bins=128):
    mono = audio.mean(axis=1)
    fft = np.fft.rfft(mono)
    mag = np.abs(fft)
    idx = np.linspace(0, len(mag)-1, bins).astype(np.int32)
    sampled = mag[idx]
    norm = sampled / (np.max(sampled) + 1e-9)
    return norm.astype(np.float32).tolist()
