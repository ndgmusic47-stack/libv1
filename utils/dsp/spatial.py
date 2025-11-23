import numpy as np


def mid_side_encode(stereo: np.ndarray):
    """
    Converts stereo [2, N] into Mid (+) and Side (-).
    """
    mid = (stereo[0] + stereo[1]) / 2
    side = (stereo[0] - stereo[1]) / 2
    return mid, side


def mid_side_decode(mid: np.ndarray, side: np.ndarray):
    """
    Converts Mid/Side back into stereo signal.
    """
    left = mid + side
    right = mid - side
    return np.vstack([left, right])


def widen(stereo: np.ndarray, amount: float = 0.25):
    """
    Widens the stereo field by scaling the Side channel.
    """
    mid, side = mid_side_encode(stereo)
    side *= (1 + amount)
    return np.clip(mid_side_decode(mid, side), -1.0, 1.0)


def narrow(stereo: np.ndarray, amount: float = 0.25):
    """
    Narrows stereo field — useful for vocals.
    """
    mid, side = mid_side_encode(stereo)
    side *= (1 - amount)
    return np.clip(mid_side_decode(mid, side), -1.0, 1.0)


def frequency_dependent_widen(stereo: np.ndarray, low_cut=200, high=12000, amount=0.2, sr=44100):
    """
    Widen only the highs and upper mids where stereo info is desirable.
    """
    left, right = stereo

    freqs = np.fft.rfftfreq(len(left), 1/sr)

    L = np.fft.rfft(left)
    R = np.fft.rfft(right)

    mask = (freqs > low_cut) & (freqs < high)
    widening = 1 + amount

    L[mask] *= widening
    R[mask] *= widening

    out_L = np.fft.irfft(L, len(left))
    out_R = np.fft.irfft(R, len(right))
    return np.clip(np.vstack([out_L, out_R]), -1.0, 1.0)


def spatial_pocket(stereo: np.ndarray, role: str):
    """
    Role-driven spatial separation strategy.
    """
    # Vocals = narrow slightly to center
    if role in ["lead_vocal", "lead", "main_vocal"]:
        stereo = narrow(stereo, amount=0.30)

    # Beat = widen for space
    elif role in ["beat", "drums", "full_mix"]:
        stereo = frequency_dependent_widen(stereo, amount=0.22)

    # Adlibs/backing = wide but less drastic
    elif role in ["adlib", "backing_vocal"]:
        stereo = widen(stereo, amount=0.18)

    return stereo


