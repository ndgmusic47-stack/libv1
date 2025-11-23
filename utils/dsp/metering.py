import numpy as np


def compute_gain_reduction(input_signal, output_signal):
    """
    Computes per-sample gain reduction curve as difference between
    input and output signal magnitudes.
    Returns float32 list.
    """
    inp = np.abs(input_signal.mean(axis=1))
    out = np.abs(output_signal.mean(axis=1))
    gr = inp - out
    gr = np.clip(gr, 0, None)
    return gr.astype(np.float32).tolist()

