import numpy as np


def apply_eq(audio_data, eq_settings, sample_rate=44100):
    """
    eq_settings = [ { "freq": x, "gain": y, "q": z }, ... ]
    """
    processed = audio_data.copy()

    for band in eq_settings:
        freq = band.get("freq", 1000)
        gain = band.get("gain", 0)
        q = band.get("q", 1.0)

        # Biquad peaking filter
        A = 10**(gain / 40)
        w0 = 2 * np.pi * freq / sample_rate
        alpha = np.sin(w0) / (2 * q)

        b0 = 1 + alpha * A
        b1 = -2 * np.cos(w0)
        b2 = 1 - alpha * A
        a0 = 1 + alpha / A
        a1 = -2 * np.cos(w0)
        a2 = 1 - alpha / A

        # Normalize
        b0 /= a0
        b1 /= a0
        b2 /= a0
        a1 /= a0
        a2 /= a0

        # Apply filter (direct form I)
        out = np.zeros_like(processed)
        x1 = x2 = y1 = y2 = 0.0

        for i, x0 in enumerate(processed):
            y0 = b0*x0 + b1*x1 + b2*x2 - a1*y1 - a2*y2
            out[i] = y0
            x2, x1 = x1, x0
            y2, y1 = y1, y0

        processed = out

    return processed

