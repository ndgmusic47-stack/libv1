import numpy as np

def stereo_widen(audio, amount=0.2):
    """
    Mid/Side widening.
    amount: 0.0–1.0
    """
    mid = (audio[:,0] + audio[:,1]) / 2
    side = (audio[:,0] - audio[:,1]) / 2
    
    side *= (1 + amount)

    L = mid + side
    R = mid - side
    
    widened = np.stack([L, R], axis=1)
    
    # Normalize if needed
    peak = np.max(np.abs(widened))
    if peak > 1:
        widened /= peak
    
    return widened

